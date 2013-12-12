# harvest rdf

from datetime import datetime
import os
import rdflib
import requests
import SPARQLWrapper
import sys
from urlparse import urlparse
import logging

try:
    from progressbar import ProgressBar, Bar, Percentage, ETA, SimpleProgress
except ImportError:
    ProgressBar = None

from belfast.rdfns import DC, SCHEMA_ORG, GEO


logger = logging.getLogger(__name__)

class HarvestRdf(object):

    URL_QUEUE = set()  # use set to ensure we avoid duplication
    PROCESSED_URLS = set()
    total = 0
    harvested = 0
    errors = 0

    _serialize_opts = {}

    def __init__(self, urls, output_dir=None, find_related=False, verbosity=1,
                 format=None, graph=None):
        self.URL_QUEUE.update(set(urls))
        self.find_related = find_related
        self.base_dir = output_dir
        self.verbosity = verbosity
        self.graph = graph

        self.format = format
        if format is not None:
            self._serialize_opts['format'] = format

        self.process_urls()

    def process_urls(self):
        if (len(self.URL_QUEUE) >= 5 or self.find_related) \
           and ProgressBar and os.isatty(sys.stderr.fileno()):
            widgets = [Percentage(), ' (', SimpleProgress(), ')',
                       Bar(), ETA()]
            progress = ProgressBar(widgets=widgets,
                                   maxval=len(self.URL_QUEUE)).start()
            processed = 0
        else:
            progress = None

        while self.URL_QUEUE:
            url = self.URL_QUEUE.pop()
            self.harvest_rdf(url)
            self.total += 1
            self.PROCESSED_URLS.add(url)
            if progress:
                progress.maxval = self.total + len(self.URL_QUEUE)
                progress.update(len(self.PROCESSED_URLS))

        if progress:
            progress.finish()

        # report if sufficient numbers:
        if self.verbosity >= 1 and (self.harvested > 5 or self.errors):
            print 'Processed %d url%s: %d harvested, %d error%s' % \
                  (len(self.PROCESSED_URLS),
                   '' if len(self.PROCESSED_URLS) == 1 else 's',
                   self.harvested, self.errors,
                   '' if self.errors == 1 else 's')

    def harvest_rdf(self, url):
        # TODO: skolemize bnodes ?

        g = self.graph.get_context(url)
        if g and len(g):
            last_modified = g.value(g.identifier, SCHEMA_ORG.dateModified)
            # TODO: use g.set(triple) to replace
            # FIXME: this is 2013-09-09
            # but
            try:
                response = requests.get(url, headers={'if-modified-since': last_modified})

                if response.status_code == requests.codes.not_modified:
                    # print '%s not modified since last harvested' % url
                    return  # nothing to do
                else:
                    # otherwise, remove the current context to avoid errors/duplication
                    self.graph.remove_context(g)

            except Exception as err:
                print 'Error attempting to load %s - %s' % (url, err)
                self.errors += 1
                return


                # last_modified = g.value(g.identifier, SCHEMA_ORG.dateModified)
                # TODO: use g.set(triple) to replace

        else:
            try:
                response = requests.get(url)
            except Exception as err:
                print 'Error attempting to load %s - %s' % (url, err)
                self.errors += 1
                return

        # g = rdflib.ConjunctiveGraph()
        # use the conjunctive graph store for persistence, url as context

        # TODO: if context already present, use last-modified from the rdf
        # and conditional GET to speed this up

        # either new or old version removed
        g = rdflib.Graph(self.graph.store, url)

        try:
            # TODO: optional flag to update everything - don't use date-modified OR cache
            # response = requests.get(url, headers={'cache-control': 'no-cache'})
            data = g.parse(data=response.content, location=url, format='rdfa')
            # NOTE: this was working previously, and should be fine,
            # but now generates an RDFa parsing error / ascii codec error
            # data = g.parse(location=url, format='rdfa')
        except Exception as err:
            print 'Error attempting to parse %s - %s' % (url, err)
            self.errors += 1
            return

        triple_count = len(data)
        # if no rdf data was found, report and return
        if triple_count == 0:
            if self.verbosity >= 1:
                print 'No RDFa data found in %s' % url
            return
        else:
            if self.verbosity > 1:
                print 'Parsed %d triples from %s' % (triple_count, url)


        # replace schema.org/dateModified with full date-time from http response
        # so we can use it for conditional get when re-harvesting
        if 'last-modified' in response.headers:
            g.set((g.identifier, SCHEMA_ORG.dateModified, rdflib.Literal(response.headers['last-modified'])))

        # TODO: add graph with context?
        if self.graph is not None:

            # automatically updates in the store
            pass
            # self.graph.addN([(s, p, o, url) for s, p, o in data])

        else:
            filename = self.filename_from_url(url)
            if self.verbosity > 1:
                print 'Saving as %s' % filename
                with open(filename, 'w') as datafile:
                    data.serialize(datafile, **self._serialize_opts)

        self.harvested += 1

        # if find related is true, look for urls related to this one
        # via either schema.org relatedLink or dcterms:hasPart
        queued = 0
        if self.find_related:
            orig_url = rdflib.URIRef(url)

            # find all sub parts of the current url (e.g., series and indexes)
            for subj, obj in data.subject_objects(predicate=DC.hasPart):
                if subj == orig_url or \
                   (subj, rdflib.OWL.sameAs, rdflib.URIRef(url)) in data:
                    related_url = unicode(obj)
                    # add to queue if not already queued or processed
                    if related_url not in self.URL_QUEUE or self.PROCESSED_URLS:
                        self.URL_QUEUE.add(related_url)
                        queued += 1

            # follow all related link relations
            for subj, obj in data.subject_objects(predicate=SCHEMA_ORG.relatedLink):
                # Technically, we may only want related links where
                # the subject is the current URL...
                # Currently, findingaids rdfa is putting that relation on the
                # archival collection object rather than the webpage object;
                # For now, go ahead and grab any relatedLink in the RDF.
                # if subj == orig_url or \
                #    (subj, rdflib.OWL.sameAs, rdflib.URIRef(url)) in data:
                related_url = unicode(obj)
                if related_url not in self.URL_QUEUE or self.PROCESSED_URLS:
                    self.URL_QUEUE.add(related_url)
                    queued += 1

        if queued and self.verbosity > 1:
            print 'Queued %d related URL%s to be harvested' % \
                  (queued, 's' if queued != 1 else '')

    def filename_from_url(self, url):
        # generate a filename based on the url (simple version)
        # NOTE: doesn't handle query string parameters, etc
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        host = host.replace('.', '_').replace(':', '-')
        path = parsed_url.path
        path = path.strip('/').replace('/', '-')
        filebase = host
        if path:
            filebase += '_%s' % path
            #  NOTE: save as .rdf since it may or may not be rdf xml
            return os.path.join(self.base_dir, '%s.%s' % (filebase, self.format))


class Annotate(object):

    def __init__(self, graph):
        self.graph = graph

        self.places()

    def places(self):
        start = datetime.now()
        res = self.graph.query('''
            PREFIX schema: <%(schema)s>
            PREFIX rdf: <%(rdf)s>
            PREFIX geo: <%(geo)s>
            SELECT DISTINCT ?uri
            WHERE {
                ?uri rdf:type schema:Place .
                FILTER NOT EXISTS {?uri geo:lat ?lat}
            }
            ''' % {'schema': SCHEMA_ORG, 'rdf': rdflib.RDF,
                   'geo': GEO}
        )
        logger.info('find places without lat/long took %s' % (datetime.now() - start))

        places = list(self.graph.subjects(predicate=rdflib.RDF.type, object=SCHEMA_ORG.Place))
        print '%d places' % len(places)

        # for p in places:
        for r in res:
            uri = r['uri']
            if not uri.startswith('http:'):
            # if isinstance(p, rdflib.BNode):
                continue

            if not self.graph.value(uri, GEO.lat):
                print uri
                try:
                    g = rdflib.Graph()
                    data = requests.get(uri, headers={'accept': 'application/rdf+xml'})
                    if data.status_code == requests.codes.ok:
                        g.parse(data=data.content)

                        # FIXME: how do we keep this in the same context? does it matter?
                        lat = g.value(uri, GEO.lat)
                        lon = g.value(uri, GEO.long)
                        print 'lat long = ', lat, lon
                        if lat:
                            self.graph.add((uri, GEO.lat, lat))
                        if lon:
                            self.graph.add((uri, GEO.long, lon))

                except Exception as err:
                    print 'Error loading %s : %s' % (uri, err)


class HarvestRelated(object):

    # sources to be harvested
    sources = [
        # NOTE: using tuples to ensure we process in this order,
        # to allow harvesting dbpedia records referenced in viaf/geonames
        # ('viaf', 'http://viaf.org/'),
        ('geonames', 'http://sws.geonames.org/'),
        ('dbpedia', 'http://dbpedia.org/'),
    ]

    def __init__(self, graph):
        self.graph = graph
        self.run()

    def run(self):
        dbpedia_sparql = SPARQLWrapper.SPARQLWrapper("http://dbpedia.org/sparql")

        # load all files into a single graph so we can query distinct
        # g = rdflib.Graph()
        # for infile in self.files:
        #     basename, ext = os.path.splitext(infile)
        #     fmt = ext.strip('.')
        #     try:
        #         g.parse(infile, format=fmt)
        #     except Exception as err:
        #         print "Error parsing '%s' as RDF -- %s" % (infile, err)
        #         continue

        for name, url in self.sources:
            # find anything that is a subject or object and has a
            # viaf, dbpedia, or geoname uri
            res = self.graph.query('''
                SELECT DISTINCT ?uri
                WHERE {
                    { ?uri ?p ?o }
                UNION
                    { ?s ?p ?uri }
                FILTER regex(str(?uri), "^%s") .
                }
            ''' % url)
            print '%d %s URI%s' % (len(res), name,
                                   's' if len(res) != 1 else '')

            if len(res) == 0:
                continue

            uris = [unicode(r['uri']).encode('ascii', 'ignore') for r in res]


            if len(uris) >= 5 and ProgressBar and os.isatty(sys.stderr.fileno()):
                widgets = [Percentage(), ' (', SimpleProgress(), ')',
                           Bar(), ETA()]
                progress = ProgressBar(widgets=widgets, maxval=len(uris)).start()
                processed = 0
            else:
                progress = None

            for u in uris:
                triple_count = len(list(self.graph.triples((rdflib.URIRef(u), None, None))))

                if triple_count > 5:
                    continue

                # print '%d triples for %s' % (
                #     len(list(self.graph.triples((rdflib.URIRef(u), None, None)))),
                #     u
                #     )

                # g = self.graph.get_context(url)
                # for now, assume if we have data we don't need to update
                # if g and len(g):
                #     print 'already have data for %s, skipping' % u
                #     continue

                # build filename based on URI
                # baseid = u.rstrip('/').split('/')[-1]

                # filename = os.path.join(datadir, '%s.%s' % (baseid, self.format))

                # if already downloaded, don't re-download but add to graph
                # for any secondary related content

                # if os.path.exists(filename):
                #     # TODO: better refinement would be to use modification
                #     # time on the file to download if changed
                #     # (do all these sources support if-modified-since headers?)

                #     # determine rdf format by file extension
                #     basename, ext = os.path.splitext(infile)
                #     fmt = ext.strip('.')
                #     try:
                #         g.parse(location=filename, format=fmt)
                #     except Exception as err:
                #         print 'Error loading file %s : %s' % (filename, err)

                g = rdflib.Graph(self.graph.store, url)

                if name == 'dbpedia':
                    # for dbpedia, use sparql query to get data we care about
                    # (request with content negotation returns extra data where
                    # uri is the subject and is also slower)
                    try:
                        dbpedia_sparql.setQuery('DESCRIBE <%s>' % u)
                        # NOTE: DESCRIBE <uri> is the simplest query that's
                        # close to what we want and returns a response that
                        # can be easily converted to an rdflib graph, but it generates
                        # too many results for records like United States, England
                        dbpedia_sparql.setReturnFormat(SPARQLWrapper.RDF)

                        # convert to rdflib graph, then filter out any triples
                        # where our uri is not the subject
                        tmp_graph =  dbpedia_sparql.query().convert()
                        for triple in tmp_graph:
                            s, p, o = triple
                            if s == rdflib.URIRef(u):
                                g.add(triple)
                                # tmp_graph.remove(triple)

                        if not len(g):
                            print 'Error: DBpedia query returned no triples for %s' % u
                            continue

                    except Exception as err:
                        print 'Error getting DBpedia data for %s : %s' % (u, err)
                        continue


                else:
                    # Use requests with content negotiation to load the data
                    data = requests.get(u, headers={'accept': 'application/rdf+xml'})

                    if data.status_code == requests.codes.ok:
                        # also add to master graph so we can download related data
                        # i.e.  dbpedia records for VIAF persons
                        # ONLY download related data for viaf (sameas dbpedia)
                        # (geonames rdf may reference multiple dbpedia without any sameAs)
                        # if name == 'viaf':

                        g.parse(data=data.content)

                        # tmp_graph = rdflib.Graph()
                        # tmp_graph.parse(data=data.content)

                    else:
                        print 'Error loading %s : %s' % (u, data.status_code)

                    # if tmp_graph:
                    #     with open(filename, 'w') as datafile:
                    #         try:
                    #             tmp_graph.serialize(datafile, format=self.format)
                    #         except Exception as err:
                    #             print 'Error serializing %s : %s' % (u, err)


                if progress:
                    processed += 1
                    progress.update(processed)

            if progress:
                progress.finish()