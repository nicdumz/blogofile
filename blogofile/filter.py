import sys
import os
import logging
import imp
import uuid

import util

logger = logging.getLogger("blogofile.filter")

from cache import bf
from cache import HierarchicalCache
import exception

bf.filter = sys.modules['blogofile.filter']

default_filter_config = {"name"        : None,
                         "description" : None,
                         "author"      : None,
                         "url"         : None}

def run_chain(chain, content):
    """Run content through a filter chain.

    Works with either a string or a sequence of filters"""
    if chain is None: 
        return content
    if not hasattr(chain, '__iter__'):
        #Not a sequence, must be a string, parse it
        chain = parse_chain(chain)
    for fn in chain:
        f = get_filter(fn)
        logger.debug("Applying filter: " + fn)
        content = f.run(content)
    logger.debug("Content: " + content)
    return util.force_unicode(content)

def parse_chain(chain):
    """Parse a filter chain into a sequence of filters"""
    parts = []
    for p in chain.split(","):
        p = p.strip()
        if p.lower() == "none":
            continue
        if len(p) > 0:
            parts.append(p)
    return parts

def preload_filters(namespace=None, directory="_filters"):
    #Find all the standalone .py files and modules in the directory
    #specified and load them into namespace specified.
    if namespace is None:
        namespace = bf.config.filters
    if(not os.path.isdir(directory)):
        return
    for fn in os.listdir(directory):
        p = os.path.join(directory,fn)
        if (os.path.isfile(p) and fn.endswith(".py")):
            #Load a single .py file:
            load_filter(fn[:-3],module_path=p,namespace=namespace)
        elif os.path.isdir(p) and os.path.isfile(os.path.join(p, "__init__.py")):
            #Load a package:
            load_filter(fn,module_path=p,namespace=namespace)

def init_filters(namespace=None):
    """Filters have an optional init method that runs before the site is 
    built"""
    if namespace is None:
        namespace=bf.config.filters
    for name, filt in namespace.items():
        if "mod" in filt \
                and type(filt.mod).__name__ == "module"\
                and not filt.mod.__initialized:
            try:
                init_method = filt.mod.init
            except AttributeError:
                filt.mod.__initialized = True
                continue
            logger.debug("Initializing filter: "+name)
            init_method()
            filt.mod.__initialized = True

def get_filter(name, namespace=None):
    #Return an already loaded filter:
    if namespace is None:
        namespace = bf.config.filters
    if namespace.has_key(name) and namespace[name].has_key("mod"):
        logger.debug("Retrieving already loaded filter: " + name)
        return namespace[name]['mod']
    else:
        raise exception.FilterNotLoaded("Filter not loaded: {0}".format(name))
            
def load_filter(name, module_path, namespace=None):
    """Load a filter from the site's _filters directory"""
    #Don't generate pyc files in the _filters directory
    #Reset the original sys.dont_write_bytecode setting where we're done
    if namespace is None:
        namespace = bf.config.filters
    try:
        initial_dont_write_bytecode = sys.dont_write_bytecode
    except KeyError:
        initial_dont_write_bytecode = False
    try:
        #Don't generate .pyc files in the _filters directory
        sys.dont_write_bytecode = True
        if module_path.endswith(".py"):
            mod = imp.load_source("{0}_{1}".format(name,uuid.uuid4()), module_path)
        else:
            mod = imp.load_package("{0}_{1}".format(name,uuid.uuid4()), module_path)
        logger.debug("Loaded filter for first time: {0}".format(module_path))
        mod.__initialized = False
        #Overwrite anything currently in this namespace:
        try:
            del namespace[name]
        except KeyError:
            pass
        #If the filter defines it's own configuration, use that as
        #it's own namespace:
        if hasattr(mod, "config") and \
                isinstance(mod.config, HierarchicalCache):
            namespace[name] = mod.config
        #Load the module into the namespace
        namespace[name].mod = mod
        #If the filter has any aliases, load those as well
        try:
            for alias in mod.config['aliases']:
                namespace[alias] = namespace[name]
        except:
            pass
        #Load the default blogofile config for filters:
        for k, v in default_filter_config.items():
            namespace[name][k] = v
        #Load any filter defined defaults:
        try:
            filter_config = getattr(mod, "config")
            for k, v in filter_config.items():
                if "." in k:
                    #This is a hierarchical setting
                    tail = namespace[name]
                    parts = k.split(".")
                    for part in parts[:-1]:
                        tail = tail[part]
                    tail[parts[-1]] = v
                else:
                    namespace[name][k] = v
        except AttributeError:
            pass
        return mod
    except:
        logger.error("Cannot load filter: "+name)
        raise
    finally:
        sys.dont_write_bytecode = initial_dont_write_bytecode
