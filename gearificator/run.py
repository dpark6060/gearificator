#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""

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

import os
import os.path as op

import sys
import shutil
from glob import glob
from importlib import import_module
from os.path import (
    join as opj,
    exists,
    dirname
)

from six import string_types

from gearificator import get_logger
from gearificator.consts import (
    # MANIFEST_BACKEND_FIELD,
    MANIFEST_CUSTOM_SECTION,
    MANIFEST_CUSTOM_OUTPUTS,
    MANIFEST_CUSTOM_INTERFACE,
    GEAR_MANIFEST_FILENAME,
    GEAR_CONFIG_FILENAME,
    GEAR_INPUTS_DIR,
    GEAR_OUTPUT_DIR
)
from gearificator.utils import (
    load_json,
    chpwd,
)

lgr = get_logger('runtime')
lgr.setLevel(10)  # DEBUG
# TODO: might want to beautify


def load_interface(module_cls):
    # import that interface and return the object
    module_name, cls_name = module_cls.split(':')  # TODO: robustify
    #topmod, submod = module_name.split('.', 1)
    module = import_module(module_name)
    return getattr(module, cls_name)


def load_interface_from_manifest(j):
    """Load the manifest.json and extract the interface definition
    """
    j = get_manifest(j)
    try:
        module_cls = j['custom'][MANIFEST_CUSTOM_SECTION][MANIFEST_CUSTOM_INTERFACE]
    except Exception:
        raise ValueError("Did not find definition of the interface among %s"
                         % str(j.get('custom')))
    return load_interface(module_cls)


def get_manifest(j):
    """Just loads manifest from a file if string provided"""
    if isinstance(j, string_types):
        # must be a filename
        j = load_json(j)
    return j


def errorout(msg, exitcode=1):
    """Report Error and exit with non-0"""
    lgr.error(msg)
    sys.exit(exitcode)


# TODO: this one is nipype specific -- so we might want to move it into nipype
def run(manifest, config, indir, outdir):
    """Given manifest, config, indir and outdir perform the execution

    Parameters
    ----------
    manifest
    config
    indir
    outdir

    Returns
    -------

    """
    # should we wrap it into a node?
    # it has .base_dir specification
    interface = None
    # TODO: we could check if config corresponds to manifest.  If not
    # (e.g. parameter in config is not known to interface/manifest config),
    # then it seems that nipype blows with cryptic/unrelated error message
    try:
        if not os.path.exists(outdir):
            os.makedirs(outdir)  # assure that exists
        # output filename might be generated relative to PWD (e.g. in fsl BET)
        # so we better cd to outdir while generating the interface
        # and for the sake of it while running
        with chpwd(outdir):
            interface = get_interface(manifest, config, indir, outdir)
            out = interface.run()
    except Exception as exc:
        lgr.error("Error while running %s: %s",
                  interface, exc)
        raise
    finally:
        # Should we clean up anything??  may be some workdir
        pass

    # Handle outputs
    # Some interfaces, e.g. fsl's FAST, would dump outputs within input directory
    # alongside original file.  So we need to move them under outdir
    for output_field in out.outputs.traits():
        try:
            output_files = getattr(out.outputs, output_field)
        except AttributeError:
            # some are some fancy events which can't be read etc
            continue
        if not output_files:
            continue
        if not isinstance(output_files, (list, tuple)):
            output_files = [output_files]
        for output_file in output_files:
            # TODO: should for any output file we do the same, not only the
            # one under indir?
            if output_file.startswith(indir):
                # need to move under outdir and flatten since not sure
                # if flywheel consumes hierarchies there
                #output_relpath = op.relpath(output_file, indir)
                target_dir = op.join(outdir, output_field)
                if not op.exists(target_dir):
                    os.mkdir(target_dir)
                target_name = op.join(target_dir, op.basename(output_file))
                lgr.debug("Moving %s under %s", output_file, outdir)
                shutil.move(output_file, op.join(outdir, target_name))

    # TODO: ATM only flat
    # outputs = glob(opj(outdir, '*'))
    # if not outputs:
    #     errorout("Yarik expected some outputs, got nothing")
    #     # But there is may be nothing really todo in our case?
    #     # May be some other interfaces would want to do something custom, we will
    #     # just save results
    return out


def get_interface(manifest, config, indir, outdir):
    """Load/parametrize and return the interface given the spec

    Parameters
    ----------
    manifest
    config
    indir
    outdir

    Returns
    -------

    """
    manifest = get_manifest(manifest)
    interface_cls = load_interface_from_manifest(manifest)
    # Prepare all kwargs to initialize that class instance
    kwargs = {}
    # Parametrize it with configuration options
    inputs = manifest.get('inputs', {})
    manifest_config = manifest.get('config', {})
    # tricky ones, yet to handle
    # probably analyze what inputs are present, and assign correspondingly
    for input_, input_params in inputs.items():
        input_dir = opj(indir, input_)
        filenames = None
        if exists(input_dir):
            filenames = glob(input_dir + '/*')
            if len(filenames) > 1:
                errorout("We do not speak multiple files yet per input")
                # TODO -- wild ideas. Provide an option to pair up
                # inputs.  E.g. if we have input/anatomy/sub{1,2,3}.nii,
                # input/mask/common.nii, input/func/sub{1,2,3}.nii
                # we could then loop nicely, and produce multiple outputs in the
                # same run.  Is it practiced in any gear?
            elif len(filenames) == 1:
                filename = filenames[0]
                kwargs[input_] = filename
        if not filenames:
            if not input_params.get('optional', False):
                lgr.warning("No input for %s was provided", input_)

    # We do need to pass defaults from manifest since we might have
    # provided custom ones
    for c, v in manifest_config.items():
        if 'default' in v:
            kwargs[c] = v['default']

    # Further configuration
    if config:
        for c, v in config.items():
            # could be a config item
            # if c not in inputs:
            #     lgr.warning(
            #         "%s is not known to inputs, which know only about %s",
            #         c, inputs.keys()
            #     )
            kwargs[c] = v

    # Treat None's which could be our annotation for not specifying any value
    # and resort to the default imposed by the tool
    for c in list(kwargs):
        if kwargs[c] is None:
            kwargs.pop(c)

    interface = interface_cls(**kwargs)

    # Now we need to get through the outputs!
    # flywheel does not yet provide options to specify outputs, so we
    # will stick them into custom:gearificator-outputs but do we need them?
    # # interface.inputs.out_file = opj(outdir, "TODO")
    # for out in manifest.get(
    #         'custom', {}).get(
    #         MANIFEST_CUSTOM_SECTION, {}).get(
    #         MANIFEST_CUSTOM_OUTPUTS, {}):
    #     # we have no clue about extension! TODO
    #     setattr(interface.outputs, out, os.path.join(outdir, out))

    # TODO: but we need to configure what is the working directory to be
    # the outputs directory so anything generated would fall in there
    return interface


def main(*args, **kwargs):
    """The main "executioner" """

    topdir = os.environ.get('FLYWHEEL')
    if not topdir and '_' in os.environ:
        # _ contains the path to the run, so whenever we try it
        # straight in the terminal, we could get our --help etc
        topdir = dirname(os.environ.get('_'))

    indir = op.abspath(opj(topdir, GEAR_INPUTS_DIR))
    outdir = op.abspath(opj(topdir, GEAR_OUTPUT_DIR))

    # Load interface
    manifest = load_json(opj(topdir, GEAR_MANIFEST_FILENAME))
    config_file = opj(topdir, GEAR_CONFIG_FILENAME)
    config = load_json(config_file).get('config', {}) \
        if os.path.exists(config_file) \
        else {}

    if '--help' in sys.argv:
        for c, d in [
            ('Inputs', manifest.get('inputs', {})),
            ('Possible Outputs', manifest.get('custom', {}).get(
                'gearificator', {}).get(
                'outputs', {})
            ),
            ('Config', manifest.get('config', {})),
        ]:
            if not d:
                continue
            print("\n%s" % c)
            for k, v in d.items():
                print(" %s: %s" % (k, v.get('description', '')))
                if c in ('Inputs', 'Config') and k in config:
                    print("  = %s" % config[k])

        return

    if '--print-manifest' in sys.argv:
        import json
        print(json.dumps(manifest, indent=2))
        return

    if '--print-config' in sys.argv:
        import json
        print(json.dumps(config, indent=2))
        return

    def pprint_dict(title, d, skip_types=None):
        print(title + ":")
        if not d:  # could be None
            return
        for k, v in sorted(d.items()):
            if not skip_types or not isinstance(v, skip_types):
                print(" %s: %s" % (k, v))

    pprint_dict("Manifest", manifest, (int, tuple, dict))
    pprint_dict("Config", config)

    # Paranoia
    outputs = glob(opj(outdir, '*'))
    if outputs:
        errorout(
            "Yarik expected no outputs being present in output dir. Got: %s"
            % ', '.join(outputs)
        )

    print('\nRunning')
    out = run(manifest, config, indir, outdir)
    # TODO: actually does not include skull file even though it is generated!
    print("\nOutputs: ")
    print(out.outputs)  # could be rendered better
    return out