from django.shortcuts import render
from django.http import HttpResponse
import json
from networkx.readwrite import json_graph, gexf
import rdflib
from StringIO import StringIO

from belfast.util import network_data, rdf_data
from belfast.rdfns import BELFAST_GROUP_URI
from belfast.groupsheets.models import RdfGroupSheet


def _network_graph():
    graph = network_data().copy()   # don't modify the original network

    rdfgraph = rdf_data()
    # filter graph by type of node
    types = ['Person', 'Organization', 'Place', 'BelfastGroupSheet']
    zeroes = 0
    for n in graph.nodes():
        if 'type' not in graph.node[n] or \
           graph.node[n]['type'] not in types:
            graph.remove_node(n)
            continue

        # use groupsheets to infer a connection between the author
        # of the groupsheet and the group itself
        if graph.node[n]['type'] == 'BelfastGroupSheet':

            sheet = RdfGroupSheet(rdfgraph, rdflib.URIRef(n))
            # FIXME: error handling when author is not in the graph?
            # should probably at least log this...
            if sheet.author and unicode(sheet.author.identifier) in graph:
                graph.add_edge(unicode(sheet.author.identifier),
                               BELFAST_GROUP_URI, weight=4)

            # remove the groupsheet itself from the network, to avoid
            # cluttering up the graph with too much information
            #graph.add_edge(n, BELFAST_GROUP_URI, weight=5)
            graph.remove_node(n)

    # AFTER filtering by type, filter out 0-degree nodes
    for n in graph.nodes():
        if len(graph.in_edges(n)) == 0 and len(graph.out_edges(n)) == 0:
            zeroes += 1
            graph.remove_node(n)

    print 'removed %d zero-degree nodes' % zeroes

    return graph


def full_js(request):
    graph = _network_graph()
    data = json_graph.node_link_data(graph)
    return HttpResponse(json.dumps(data), content_type='application/json')


def full_gexf(request):
    graph = _network_graph()
    buf = StringIO()
    gexf.write_gexf(graph, buf)
    response = HttpResponse(buf.getvalue(), content_type='application/gexf+xml')
    response['Content-Disposition'] = 'attachment; filename=belfastgroup.gexf'
    return response


def full(request):
    return render(request, 'network/graph.html')


def group_people(request):
    return render(request, 'network/bg.html',
                  {'bg_uri': BELFAST_GROUP_URI})


def group_people_js(request):
    # FIXME: significant overlap with full_js above
    graph = network_data().copy()   # don't modify the original network

    rdfgraph = rdf_data()
    # restrict to people and belfast group ONLY
    zeroes = 0
    # connect groupsheet authors to the group
    for n in graph.nodes():
        # use groupsheets to infer a connection between the author
        # of the groupsheet and the group itself
        if 'type' in graph.node[n] and graph.node[n]['type'] == 'BelfastGroupSheet':

            sheet = RdfGroupSheet(rdfgraph, rdflib.URIRef(n))
            # FIXME: error handling when author is not in the graph?
            # should probably at least log this...
            if sheet.author and unicode(sheet.author.identifier) in graph:
                graph.add_edge(unicode(sheet.author.identifier),
                               BELFAST_GROUP_URI, weight=4)

            # remove the groupsheet itself from the network, to avoid
            # cluttering up the graph with too much information
            #graph.add_edge(n, BELFAST_GROUP_URI, weight=5)
            graph.remove_node(n)

    # now filter to just belfast group & people
    for n in graph.nodes():
        if n == BELFAST_GROUP_URI:
            # cheating here (something in FA code is wrong)
            graph.node[n]['type'] = 'Organization'
            continue

        if ('type' not in graph.node[n] or
           graph.node[n]['type'] != 'Person'):
            graph.remove_node(n)

    # remove any edges that don't involve the belfast group
    # FIXME: this makes the graph *very* small
    for edge in graph.edges():
        if BELFAST_GROUP_URI not in edge:
            graph.remove_edge(*edge)

    # AFTER filtering by type, filter out 0-degree nodes
    for n in graph.nodes():
        if len(graph.in_edges(n)) == 0 and len(graph.out_edges(n)) == 0:
            zeroes += 1
            graph.remove_node(n)
    print 'removed %d zero-degree nodes' % zeroes


    data = json_graph.node_link_data(graph)
    return HttpResponse(json.dumps(data), content_type='application/json')


