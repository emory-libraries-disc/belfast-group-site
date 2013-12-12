#!/usr/bin/env python

# script to harvest and prep entire dataset, start to finish

from optparse import make_option
import os
import rdflib

from django.conf import settings
from django.core.management.base import BaseCommand

from belfast.data.harvest import HarvestRdf, Annotate # HarvestRelated
from belfast.data.qub import QUB
from belfast.data.clean import SmushGroupSheets, IdentifyGroupSheets, \
    InferConnections
from belfast.data.nx import Rdf2Gexf


class Command(BaseCommand):
    '''Harvest and prep Belfast Group RDF dataset'''
    help = __doc__

    v_normal = 1

    option_list = BaseCommand.option_list + (
        make_option('-H', '--harvest', action='store_true', help='Harvest RDFa'),
        make_option('-q', '--queens', action='store_true',
            help='Convert Queens University Belfast collection to RDF'),
        make_option('-r', '--related', action='store_true',
            help='Harvest related RDF from VIAF, GeoNames, and DBpedia'),
        make_option('-i', '--identify', action='store_true',
            help='Identify group sheets'),
        make_option('-s', '--smush', action='store_true',
            help='Smush groupsheet URIs'),
        make_option('-c', '--connect', action='store_true',
            help='Infer and make connections implicit in the data'),
        make_option('-g', '--gexf', action='store_true',
            help='Generate GEXF network graph data')
    )

    # eadids for documents with tagged names
    eadids = ['longley744', 'ormsby805', 'irishmisc794', 'carson746',
              'heaney960', 'heaney653', 'muldoon784', 'simmons759',
              'hobsbaum1013', 'mahon689', 'fallon817', 'grennan1150',
              'heaney-hammond1019', 'hughes644', 'mcbreen1088',
              'monteith789', 'deane1210']
    # NOTE: once in production, related collections links should help

    # RDF from TEI group sheets
    tei_ids = ['longley1_10244', 'longley1_10353', 'heaney1_10407',
               'carson1_1035', 'longley1_10202', 'heaney1_10415',
               'heaney1_10365', 'heaney1_10163', 'heaney1_10199',
               'heaney1_10236', 'heaney1_10269', 'longley1_1042',
               'heaney1_10442', 'hobsbaum1_1040', 'heaney1_10116',
               'heaney1_1078', 'heaney1_1041', 'muldoon2_10121',
               'muldoon2_1079', 'muldoon2_1040', 'longley1_10120',
               'longley1_10158', 'longley1_1079', 'longley1_10282',
               'longley1_10316', 'simmons1_1035', 'simmons1_1069',
               'hobsbaum1_1047']

    # for now, harvest from test FA site
    harvest_urls = ['http://testfindingaids.library.emory.edu/documents/%s/' % e
                    for e in eadids]
    # using local dev urls for now
    harvest_urls.extend(['http://localhost:8000/groupsheets/%s/' % i for i in tei_ids])

    QUB_input = os.path.join(settings.BASE_DIR, 'data', 'fixtures', 'QUB_ms1204.html')
    # FIXME: can we find a better url for the Queen's Belfast Group collection ?
    QUB_URL = 'http://www.qub.ac.uk/directorates/InformationServices/TheLibrary/FileStore/Filetoupload,312673,en.pdf'

    def handle(self, *args, **options):
        self.verbosity = options['verbosity']

        # if specific steps are specified, run only those
        # otherwise, run all steps
        all_steps = not any([options['harvest'], options['queens'],
                             options['related'], options['smush'],
                             options['gexf'], options['identify'],
                             options['connect']])

        # initialize graph persistence
        graph = rdflib.ConjunctiveGraph('Sleepycat')
        graph.open(settings.RDF_DATABASE, create=True)

        if all_steps or options['harvest']:
            self.stdout.write('-- Harvesting RDF from EmoryFindingAids related to the Belfast Group')

            HarvestRdf(self.harvest_urls,
                       find_related=True, verbosity=0, #format=output_format,
                       graph=graph)

        if all_steps or options['queens']:
            self.stdout.write('-- Converting Queens University Belfast Group collection description to RDF')
            QUB(self.QUB_input, verbosity=0, graph=graph, url=self.QUB_URL)

        if all_steps or options['related']:
            # FIXME: no longer quite accurate or what we need;
            # to keep rdf dataset as small as possible, should *only* grab attributes
            # we actually need to run the site
            self.stdout.write('-- Annotating raph with related information from VIAF, GeoNames, and DBpedia')
            Annotate(graph)
            # HarvestRelated(graph)   # old harvest , which is pulling too much data

        if all_steps or options['identify']:
            # smush any groupsheets in the data
            self.stdout.write('-- Identifying groupsheets')
            IdentifyGroupSheets(graph)

        if all_steps or options['smush']:
            # smush any groupsheets in the data
            self.stdout.write('-- Smushing groupsheet URIs')
            SmushGroupSheets(graph)

        if all_steps or options['connect']:
            # infer connections
            self.stdout.write('-- Inferring connections: groupsheet authors affiliated with group')
            InferConnections(graph)
            # TODO: groupsheet owner based on source collection

        if all_steps or options['gexf']:
            # generate gexf
            self.stdout.write('-- Generating network graph and saving as GEXF')
            Rdf2Gexf(graph, settings.GEXF_DATA)

        # TODO: create rdf profiles with local uris; get rid of person db model

        graph.close()