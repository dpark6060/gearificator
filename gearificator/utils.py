import json
import os
from os.path import (
    basename,
    isabs,
    normpath,
    dirname,
    join as opj,
)
import sys

from . import get_logger
lgr = get_logger('utils')


def getpwd():
    """Try to return a CWD without dereferencing possible symlinks

    If no PWD found in the env, output of getcwd() is returned
    """
    try:
        return os.environ['PWD']
    except KeyError:
        return os.getcwd()


class chpwd(object):
    """Wrapper around os.chdir which also adjusts environ['PWD']

    The reason is that otherwise PWD is simply inherited from the shell
    and we have no ability to assess directory path without dereferencing
    symlinks.

    If used as a context manager it allows to temporarily change directory
    to the given path
    """
    def __init__(self, path, mkdir=False, logsuffix=''):

        if path:
            pwd = getpwd()
            self._prev_pwd = pwd
        else:
            self._prev_pwd = None
            return

        if not isabs(path):
            path = normpath(opj(pwd, path))
        if not os.path.exists(path) and mkdir:
            self._mkdir = True
            os.mkdir(path)
        else:
            self._mkdir = False
        lgr.debug("chdir %r -> %r %s", self._prev_pwd, path, logsuffix)
        os.chdir(path)  # for grep people -- ok, to chdir here!
        os.environ['PWD'] = path

    def __enter__(self):
        # nothing more to do really, chdir was in the constructor
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._prev_pwd:
            # Need to use self.__class__ so this instance, if the entire
            # thing mocked during the test, still would use correct chpwd
            self.__class__(self._prev_pwd, logsuffix="(coming back)")


def load_json(filename, must_exist=True):
    if not os.path.exists(filename):
        if not must_exist:
            return {}
        else:
            raise ValueError("File %s does not exist!" % filename)
    with open(filename) as f:
        return json.load(f, encoding='utf-8')


#
# Additional handlers
#
_sys_excepthook = sys.excepthook  # Just in case we ever need original one


def is_interactive():
    """Return True if all in/outs are tty"""
    # TODO: check on windows if hasattr check would work correctly and add value:
    #
    return sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()


def setup_exceptionhook(ipython=False):
    """Overloads default sys.excepthook with our exceptionhook handler.

       If interactive, our exceptionhook handler will invoke
       pdb.post_mortem; if not interactive, then invokes default handler.
    """

    def _pdb_excepthook(type, value, tb):
        import traceback
        traceback.print_exception(type, value, tb)
        print()
        if is_interactive():
            import pdb
            pdb.post_mortem(tb)

    if ipython:
        from IPython.core import ultratb
        sys.excepthook = ultratb.FormattedTB(mode='Verbose',
                                             # color_scheme='Linux',
                                             call_pdb=is_interactive())
    else:
        sys.excepthook = _pdb_excepthook


def import_module_from_file(modpath, log=lgr.debug):
    """Import provided module given a path
    """
    assert(modpath.endswith('.py'))  # for now just for .py files
    dirname_ = dirname(modpath)

    try:
        log("Importing %s" % modpath)
        sys.path.insert(0, dirname_)
        modname = basename(modpath)[:-3]
        mod = __import__(modname, level=0)
        return mod
    except Exception as e:
        raise RuntimeError(
            "Failed to import module from %s: %s" % (modpath, e))
    finally:
        if dirname_ in sys.path:
            sys.path.pop(sys.path.index(dirname_))
        else:
            log("Expected path %s to be within sys.path, but it was gone!"
                % dirname_)


class PathRoot(object):
    """Find the root of paths based on a predicate function.

    The path -> root mapping is cached across calls.

    Parameters
    ----------
    predicate : callable
        A callable that will be passed a path and should return true
        if that path should be considered a root.

    Acknowledgement
    ---------------
    Borrowed from NICEMAN.utils under MIT license
    """

    def __init__(self, predicate):
        self._pred = predicate
        self._cache = {}  # path -> root

    def __call__(self, path):
        """Find root of `path` based on `predicate`.

        Parameters
        ----------
        path : str
            Find this path's root.

        Returns
        -------
        str or None
        """
        to_cache = []
        root = None
        for pth in self._walk_up(path):
            if pth in self._cache:
                root = self._cache[pth]
                break

            to_cache.append(pth)

            if self._pred(pth):
                root = pth
                break

        for pth in to_cache:
            self._cache[pth] = root
        return root

    @staticmethod
    def _walk_up(path):
        """Yield PATH, chopping off the right-most directory each iteration.

        Parameters
        ----------
        path : string
        """
        while path not in [os.path.pathsep, os.path.sep, ""]:
            yield path
            path = os.path.dirname(path)


def md5sum(filename):
    import hashlib
    with open(filename, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()
