'''
sbml2sbol (c) University of Liverpool. 2019

sbml2sbol is licensed under the MIT License.

To view a copy of this license, visit <http://opensource.org/licenses/MIT/>.

@author:  neilswainston
'''
# pylint: disable=invalid-name
# pylint: disable=too-many-arguments
# pylint: disable=too-many-nested-blocks
from collections import defaultdict
import os.path
import sys
import glob

import libsbml
from sbol import setHomespace, ComponentDefinition, Config, Document, \
    SO_CDS, SO_RBS  # , FloatProperty, URIProperty
from synbiochem.utils import io_utils, dna_utils


Config.setOption('validate', False)


def convert(sbml_filepaths, sbol_filename, rbs, max_prot_per_react=3,
            tirs=None, pathway_id='rp_pathway'):
    """Convert an rpSBML file to a SBOL file

    :param sbml_filepaths: The path to the rpSBML file
    :param sbol_filename: The path to the SBOL file
    :param rbs: Calculate or not the RBS strength
    :param max_prot_per_react: The maximum number of proteins per reaction (Default: 3)
    :param tirs: The RBS strength values
    :param pathway_id: The Groups id of the heterologous pathway

    :type sbml_filepaths: str
    :type sbol_filename: str
    :type rbs: bool
    :type max_prot_per_react: int
    :type tirs: list
    :type pathway_id: str

    :rtype: None
    :return: None
    """
    if rbs:
        tirs = [10000, 20000, 30000] if tirs is None else tirs
    else:
        tirs = None

    model_rct_uniprot = _read_sbml(sbml_filepaths, pathway_id)

    doc = _convert(model_rct_uniprot, tirs, max_prot_per_react)

    dir_name = os.path.dirname(os.path.abspath(sbol_filename))

    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

    doc.write(sbol_filename)


def _read_sbml(sbml_filepaths, pathway_id):
    """Read an rpSBML file

    :param sbml_filepaths: The path to the rpSBML file
    :param pathway_id: The Groups id of the heterologous pathway

    :type sbml_filepaths: str
    :type pathway_id: str

    :rtype: dict
    :return: The collection of UNIPROT id's contained within a rpSBML file
    """
    rct_uniprot = defaultdict(list)

    #for filename in io_utils.get_filenames(sbml_filepaths):
    for filename in glob.glob(sbml_filepaths+'/*.xml'):
        document = libsbml.readSBMLFromFile(filename)
        rp_pathway = document.model.getPlugin('groups').getGroup(pathway_id)

        for member in rp_pathway.getListOfMembers():
            if not member.getIdRef() == 'targetSink':
                # Extract reaction annotation:
                annot = document.model.getReaction(
                    member.getIdRef()).getAnnotation()
                bag = annot.getChild('RDF').getChild(
                    'BRSynth').getChild('brsynth')

                for i in range(bag.getNumChildren()):
                    ann = bag.getChild(i)

                    if ann.getName() == 'selenzyme':
                        for j in range(ann.getNumChildren()):
                            sel_ann = ann.getChild(j)
                            rct_uniprot[member.getIdRef()].append(
                                sel_ann.getName())

    return rct_uniprot


def _convert(rct_uniprot, tirs, max_prot_per_react):
    """Convert the collection of UNIPROT id's within a rpSBML file to sequences

    :param rct_uniprot: The dict result of UNIPROT id's from a rpSBML
    :param tirs: The RBS strength values
    :param max_prot_per_react: The maximum number of proteins per reaction (Default: 3)

    :type rct_uniprot: dict
    :type max_prot_per_react: int
    :type rbs: bool
    :type tirs: list

    :rtype: Document 
    :return: The SBOL document object
    """
    setHomespace('http://liverpool.ac.uk')
    doc = Document()

    for rct, uniprot_ids_set in rct_uniprot.items():
        # Specify uniprot-specific assembly region placeholders:
        # (Provides consistent assembly sequence for each reaction group.)
        _5p_assembly = ComponentDefinition('%s_5_prime_assembly' % rct)
        _5p_assembly.roles = dna_utils.SO_ASS_COMP
        _3p_assembly = ComponentDefinition('%s_3_prime_assembly' % rct)
        _3p_assembly.roles = dna_utils.SO_ASS_COMP

        doc.addComponentDefinition([_5p_assembly, _3p_assembly])

        for uniprot_id in uniprot_ids_set[:max_prot_per_react]:
            if tirs:
                for tir in tirs:
                    _add_gene(doc, uniprot_id, tir, _5p_assembly, _3p_assembly)
            else:
                _add_gene(doc, uniprot_id, None, _5p_assembly, _3p_assembly)

    return doc


def _add_gene(doc, uniprot_id, tir, _5p_assembly, _3p_assembly):
    """Add the gene to the appropriate SBOL placeholders

    :param doc: SBOL document object
    :param uniprot_id: The list of uniprot id's 
    :param tir: The rbs strenth list
    :param _5p_assembly: 5 prime dna assembly region placeholder
    :param _3p_assembly: 3 prime dna assembly region placeholder
    
    :type doc: Document
    :type uniprot_id: list
    :type tir: list
    :type _5p_assembly: dna_utils.SO_ASS_COMP
    :type _3p_assembly: dna_utils.SO_ASS_COMP
    
    :rtype: None
    :return: None
    """
    # Add placeholder for top-level gene:
    gene = ComponentDefinition('%s_%s_gene' % (uniprot_id, tir))
    gene.roles = dna_utils.SO_GENE

    # URIProperty(gene,
    #            'http://biomodels.net/biologyqualifiers#isInstanceOf',
    #            '0', '1',
    #            'http://identifiers.org/uniprot/%s' % uniprot_id)

    # Add placeholders for RBS and CDS:
    if tir:
        rbs = ComponentDefinition('%s_%s_rbs' % (uniprot_id, tir))
        rbs.roles = SO_RBS
        rbs = _add_comp_def(doc, rbs)
    else:
        rbs = None

    # FloatProperty(
    #    rbs, 'http://liverpool.ac.uk#target_tir', '0', '1', tir)

    cds = ComponentDefinition('%s_%s_cds' % (uniprot_id, tir))
    cds.roles = SO_CDS

    # URIProperty(cds,
    #            'http://biomodels.net/biologyqualifiers#isInstanceOf',
    #            '0', '1',
    #            'http://identifiers.org/uniprot/%s' % uniprot_id)

    # Add ComponentDefintion if it has not yet been added:
    cds = _add_comp_def(doc, cds)

    # Assemble gene from features:
    gene = _add_comp_def(doc, gene)

    assembly = [_5p_assembly, rbs, cds, _3p_assembly] if rbs \
        else [_5p_assembly, cds, _3p_assembly]

    gene.assemblePrimaryStructure(assembly)


def _add_comp_def(doc, comp_def):
    """Add the component definition while checking if it already existss

    :param doc: The SBOL Document object
    :param comp_def: Component definition
    
    :type doc: Document
    :type comp_def: ComponentDefinition
    
    :rtype: ComponentDefinition
    :return: The updated component definition
    """
    if comp_def.identity not in [comp_def.identity
                                 for comp_def in doc.componentDefinitions]:
        doc.addComponentDefinition(comp_def)
    else:
        comp_def = doc.getComponentDefinition(comp_def.identity)

    return comp_def


def main(args):
    """Access the conversion using the command line

    :param args: Arguments
    
    :type args: list
    
    :rtype: None
    :return: None
    """
    convert(args[2:], args[1], args[0].lower() == 'true')


if __name__ == '__main__':
    main(sys.argv[1:])
