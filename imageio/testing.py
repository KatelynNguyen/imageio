# -*- coding: utf-8 -*-
# Copyright (c) 2014, Imageio team
# Distributed under the (new) BSD License. See LICENSE.txt for more info.

""" Functionality used for testing. This code itself is not covered in tests.
"""

from __future__ import absolute_import, print_function, division

import os
import sys
import inspect
import shutil
import atexit

import pytest
from _pytest import runner

# Get root dir
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = THIS_DIR
for i in range(9):
    ROOT_DIR = os.path.dirname(ROOT_DIR)
    if os.path.isfile(os.path.join(ROOT_DIR, '.gitignore')):
        break


## Functions to use in tests

def run_tests_if_main(show_coverage=False):
    """ Run tests in a given file if it is run as a script
    
    Coverage is reported for running this single test. Set show_coverage to
    launch the report in the web browser.
    """
    local_vars = inspect.currentframe().f_back.f_locals
    if not local_vars.get('__name__', '') == '__main__':
        return
    # we are in a "__main__"
    os.chdir(ROOT_DIR)
    fname = str(local_vars['__file__'])
    _clear_imageio()
    _enable_faulthandler()
    pytest.main('-v -x --color=yes --cov imageio '
                '--cov-config .coveragerc --cov-report html %s' % fname)
    if show_coverage:
        import webbrowser
        fname = os.path.join(ROOT_DIR, 'htmlcov', 'index.html')
        webbrowser.open_new_tab(fname)


_the_test_dir = None


def get_test_dir():
    global _the_test_dir
    if _the_test_dir is None:
        # Define dir
        from imageio.core import appdata_dir
        _the_test_dir = os.path.join(appdata_dir('imageio'), 'testdir')
        # Clear it now
        if os.path.isdir(_the_test_dir):
            shutil.rmtree(_the_test_dir)
        os.makedirs(_the_test_dir)
        # And later
        atexit.register(lambda x=None: shutil.rmtree(_the_test_dir))
    return _the_test_dir


## Functions to use from make

def test_unit(cov_report='term'):
    """ Run all unit tests. Returns exit code.
    """
    orig_dir = os.getcwd()
    os.chdir(ROOT_DIR)
    try:
        _clear_imageio()
        _enable_faulthandler()
        return pytest.main('-v --cov imageio --cov-config .coveragerc '
                           '--cov-report %s tests' % cov_report)
    finally:
        os.chdir(orig_dir)


def test_style():
    """ Test style using flake8
    """
    # Test if flake is there
    try:
        from flake8.main import main  # noqa
    except ImportError:
        print('Skipping flake8 test, flake8 not installed')
        return
    
    # Reporting
    print('Running flake8 on %s' % ROOT_DIR)
    sys.stdout = FileForTesting(sys.stdout)
    
    # Init
    ignores = ['E226', 'E241', 'E265', 'W291', 'W293']
    fail = False
    count = 0
    
    # Iterate over files
    for dir, dirnames, filenames in os.walk(ROOT_DIR):
        dir = os.path.relpath(dir, ROOT_DIR)
        # Skip this dir?
        exclude_dirs = set(['.git', 'docs', 'build', 'dist', '__pycache__'])
        if exclude_dirs.intersection(dir.split(os.path.sep)):
            continue
        # Check all files ...
        for fname in filenames:
            if fname.endswith('.py'):
                # Get test options for this file
                filename = os.path.join(ROOT_DIR, dir, fname)
                skip, extra_ignores = _get_style_test_options(filename)
                if skip:
                    continue
                # Test
                count += 1
                thisfail = _test_style(filename, ignores + extra_ignores)
                if thisfail:
                    fail = True
                    print('----')
                sys.stdout.flush()
    
    # Report result
    sys.stdout.revert()
    if not count:
        raise RuntimeError('    Arg! flake8 did not check any files')
    elif fail:
        raise RuntimeError('    Arg! flake8 failed (checked %i files)' % count)
    else:
        print('    Hooray! flake8 passed (checked %i files)' % count)


## Requirements

def _enable_faulthandler():
    """ Enable faulthandler (if we can), so that we get tracebacks
    on segfaults.
    """
    try:
        import faulthandler
        faulthandler.enable()
        print('Faulthandler enabled')
    except Exception:
        print('Could not enable faulthandler')


def _clear_imageio():
    # Remove ourselves from sys.modules to force an import
    for key in list(sys.modules.keys()):
        if key.startswith('imageio'):
            del sys.modules[key]


class FileForTesting(object):
    """ Alternative to stdout that makes path relative to ROOT_DIR
    """
    def __init__(self, original):
        self._original = original
    
    def write(self, msg):
        if msg.startswith(ROOT_DIR):
            msg = os.path.relpath(msg, ROOT_DIR)
        self._original.write(msg)
        self._original.flush()
    
    def flush(self):
        self._original.flush()
    
    def revert(self):
        sys.stdout = self._original


def _get_style_test_options(filename):
    """ Returns (skip, ignores) for the specifies source file.
    """
    skip = False
    ignores = []
    text = open(filename, 'rb').read().decode('utf-8')
    # Iterate over lines
    for i, line in enumerate(text.splitlines()):
        if i > 20:
            break
        if line.startswith('# styletest:'):
            if 'skip' in line:
                skip = True
            elif 'ignore' in line:
                words = line.replace(',', ' ').split(' ')
                words = [w.strip() for w in words if w.strip()]
                words = [w for w in words if 
                         (w[1:].isnumeric() and w[0] in 'EWFCN')]
                ignores.extend(words)
    return skip, ignores


def _test_style(filename, ignore):
    """ Test style for a certain file.
    """
    if isinstance(ignore, (list, tuple)):
        ignore = ','.join(ignore)
    
    orig_dir = os.getcwd()
    orig_argv = sys.argv
    
    os.chdir(ROOT_DIR)
    sys.argv[1:] = [filename]
    sys.argv.append('--ignore=' + ignore)
    try:
        from flake8.main import main
        main()
    except SystemExit as ex:
        if ex.code in (None, 0):
            return False
        else:
            return True
    finally:
        os.chdir(orig_dir)
        sys.argv[:] = orig_argv


## Patching

def pytest_runtest_call(item):
    """ Variant of pytest_runtest_call() that stores traceback info for
    postmortem debugging.
    """
    try:
        runner.pytest_runtest_call_orig(item)
    except Exception:
        type, value, tb = sys.exc_info()
        tb = tb.tb_next  # Skip *this* frame
        sys.last_type = type
        sys.last_value = value
        sys.last_traceback = tb
        del tb  # Get rid of it in this namespace
        raise

# Monkey-patch pytest
if not runner.pytest_runtest_call.__module__.startswith('imageio'):
    runner.pytest_runtest_call_orig = runner.pytest_runtest_call
    runner.pytest_runtest_call = pytest_runtest_call