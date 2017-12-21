#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:
"""Interfaces and workflows of Nipype

 COPYRIGHT: Yaroslav Halchenko 2017

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

from __future__ import absolute_import

import nipype
import re
from collections import OrderedDict
from nipype.interfaces.base import traits

from . import nipype_handlers

# TODO: Should become part of some kind of a recipe
#       which would prescribe the environment and then what
#       interface is being gearified, with possible tune ups and options
DOCKER_BASE_IMAGE = "neurodebian:stretch"
#DOCKER_IMAGE = "gearificator:ants-test"  # neurodebian:stretch"
DEB_PACKAGES = [
    'ants',  # possibly versioned   ants=2.2.0-1
    'python-nipype',  # probably actually would need pip install it
]
PIP_PACKAGES = [
    # most likely we will need master of nipype for a while
    # if we are to contribute/extend docs etc
    # 'git+https://github.com/nipy/nipype'
]
LICENSE = ['BSD-3-Clause']
# not needed here but in general, should be a part of the specific
# recipe, depends on the app/pkg/etc
# SOURCE_FILE =
# ADD_PATH =

import logging
lgr = logging.getLogger('gearificator.nipype')


def get_version():
    import nipype
    return ".nipype.%s" % nipype.__version__


def analyze_spec(spec_cls, defaults={}):
    """Given the Spec class, extract the instances and interesting fields"""
    spec = spec_cls()
    config = OrderedDict()
    inputs = OrderedDict()
    for opt, trait in spec.items():
        # We better skip some, at least for now,
        # TODO: some might be specific to interfaces or too generic for which
        # we do not care to expose in the gear ATM
        if opt in {
            'ignore_exception',
            'terminal_output',
            'environ',
        }:
            continue
        try:
            handler, handler_name = get_trait_handler(trait)
        except ValueError as exc:
            lgr.warning("No handler for %s: %s", opt, exc)
            continue
        if not handler:
            continue

        trait_rec = handler(trait, default=defaults.get(opt))
        if trait_rec:
            desc = trait_rec.get('description')
            if not desc or desc.startswith(' [default'):
                # quite often options are "self-descriptive" so we will take the name
                # and use it as a description with minor changes
                new_desc = opt.capitalize().replace('_', ' ')
                # TODO: move into a function.  Add tune ups like  Num (of)? -> Number of
                if desc:
                    # add back the default
                    new_desc += desc
                trait_rec['description'] = new_desc
        if trait_rec is None:
            lgr.warning("Handler returned None for %s of trait %s", opt, trait)
        else:
            (inputs
             if handler_name in {'File', 'InputMultiPath'}
             else config
             )[opt] = trait_rec
            #(inputs if handler_name in {'File', 'InputMultiPath'} else config)[opt] = trait_rec
    return config, inputs


def get_trait_handler(trait):
    """Given a trait, return a handler and its name
    """
    trait_type_class = trait.trait_type.__class__
    trait_type = trait_type_class.__name__
    # strip/change prefixes
    handler_name = trait_type.replace('traits.trait_types.', '')
    handler_name = handler_name.replace('nipype.interfaces.base.', 'nipype_')
    handler = getattr(nipype_handlers, handler_name, None)
    if not handler:
        raise ValueError("No handler for %s" % handler_name)
    return handler, handler_name


def extract_manifest(cls, defaults={}):
    """

    Parameters
    ----------
    cls
      Class to extract the manifest from/for

    Returns
    -------

    """
    # will be a mix of options and "inputs" (identified by using Files)
    config, inputs = analyze_spec(cls.input_spec, defaults=defaults)
    #  Not yet sure if actually needed right here since outputs are not
    #  part of the manifest
    config_out, outputs = analyze_spec(cls.output_spec, defaults=defaults)
    assert not config_out, "expecting only files in the output, not config settings"
    # strip outputs of unneeded fields
    # may be eventually we would bring some back
    for v in outputs.values():
        for f in 'base', 'optional':
            v.pop(f, None)
    # TODO: in some cases outputs might have the same field as
    # declared in inputs (e.g. 'out_file' in BET). How do we deal with it?
    # One way is at the run time, in case user specified that one,
    # we use it somehow
    manifest = OrderedDict()

    manifest['author'] = None
    manifest['name'] = cls.__name__.lower()
    # TODO: fill out what we could about stuff
    # TODO: 'custom':'docker-image'
    #manifest['author'] = 'Some authors, possibly from a recipe/API'
    #manifest['description'] = 'Some description, e.g. %s' % cls.__doc__
    cls_doc = getattr(cls, '__doc__')
    if cls_doc:
        # take the first line as a description
        manifest['description'] = cls_doc.split('\n')[0]

    manifest['config'] = config or {}
    manifest['inputs'] = inputs or {}

    manifest['url'] = "http://nipype.readthedocs.io/en/%s/interfaces/generated/interfaces.ants/registration.html" % nipype.__version__
    # TODO:  license -- we should add the license for the piece?

    return manifest, outputs