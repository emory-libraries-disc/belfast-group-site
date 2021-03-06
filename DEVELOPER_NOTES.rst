Developer Notes
===============

RDF database
------------

Occasionally the RDF database will run into memory errors in production,
or you may see an error like this when running under Django runserver::

    AttributeError: 'Sleepycat' object has no attribute '_Sleepycat__sync_thread'

The simple solution that usually works is to delete the `__db.00[123]`
files from the rdf database directory.  This doesn't remove any of the
actual graph data, and should allow the database to be reloaded without
memory errors.


RDF and graph data
------------------

If you are just doing maintenance on the belfast site and don't need to
work on the scripts that harvest and process the rdf data, you can set
up your development site with the releasted production data.

Download the GEXF files and belfastrdf_full.rdf.gz from
`Release 1.0.3 <https://github.com/emory-libraries-ecds/belfast-group-site/releases/tag/1.0.3>`_.

The GEXF files should be placed in a `gexf` directory in the top level
of your project (paths and filenames are configurable in settings).

The GEXF and the the belfast rdf dump should be edited so that site URIs
will be local to your project.  Replace
**http://belfastgroup.digitalscholarship.emory.edu/** with
**http://localhost:8000/** or whatever your development url will be.
You must also configure your default Site in django admin to match the same url.

Use the **loadrdf** manage command to load the edited RDF data.

Note that by default, profiles are not listed unless a photo is loaded
in the django admin.  This can be overridden by setting
**REQUIRE_PROFILE_PICTURE** to `False` in `localsettings.py`.


Running tests
-------------

Unit tests shoud be run with the ``REUSE_DB=1`` environment variable set,
so that Django does not to try recreate the RDF test database (this causes
errors, since the RDF database does not support cursors, etc).  You can
also use the ``fab test`` command, which includes this option.