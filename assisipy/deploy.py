#!/usr/bin/env python
# -*- coding: utf-8 -*-

import yaml
import pygraphviz as pgv
from fabric.api import run, put, settings
import warnings

import argparse
import os
import shutil


""" Tools for automatically deploying CASU controllers. """

'''
Note on handling warnings:

There is a known bug in an upstream library, Crypto/blockalg. It is used by
the paramiko library, which is used in fabric.

The warnings are filtered out in this tool, using high specificity; if the
version of paramiko or Crypto change (within aptitude repos for ubuntu 16.04 at
the time of writing) or are used differently, this might not catch the warning.


The strategy here uses a `catch_warnings` context manager [1], and filters for
FutureWarnings only in a specific library on a specific line. See [2] for how
to update.

A more basic filtering can drop ALL FutureWarnings from all packages
    warnings.simplefilter("ignore", FutureWarning)
but instead we here define the module and line to ensure new warnings are not
blindly hidden.

    warnings.filterwarnings(
        action="ignore", category=FutureWarning, module="Crypto", lineno=141)


[1] https://docs.python.org/2/library/warnings.html#available-context-managers
[2] https://docs.python.org/2/library/warnings.html#the-warnings-filter

'''

class Deploy:
    """
    Class for performing deployment tasks.
    """

    def __init__(self, project_file_name):
        """
        Parses the configuration files and initializes internal data structures.
        """
        self.proj_name = os.path.splitext(os.path.basename(project_file_name))[0]
        self.project_root = os.path.dirname(os.path.abspath(project_file_name))
        self.sandbox_dir = self.proj_name + '_sandbox'
        self.fabfile_name = os.path.join(self.sandbox_dir, self.proj_name + '.py')

        self.arena = {}
        self.nbg = None
        self.dep = {}


        self.prepared = False

        with open(project_file_name) as project_file:
            project = yaml.safe_load(project_file)

        # Read the .arena file
        with open(os.path.join(self.project_root, project['arena'])) as arena_file:
            self.arena = yaml.safe_load(arena_file)

        # Read the neighborhood graph, so long as one is defined.
        nbg_fname = project.get('nbg', None)
        if nbg_fname is not None and nbg_fname.lower() not in ['none', 'null']:
            # if one was missed but not explicitly so, should emit warning?
            self.nbg = pgv.AGraph(os.path.join(self.project_root, nbg_fname))


        # Read the deployment file
        with open(os.path.join(self.project_root, project['dep'])) as dep_file:
            self.dep = yaml.safe_load(dep_file)

    def prepare(self, layer_select='all', allow_partial=False):
        """
        Prepare deployment in local folder.
        """

        cwd = os.getcwd()
        print('Changing directory to {0}'.format(self.project_root))
        os.chdir(self.project_root)
        print('Preparing files for deployment!')

        # Remove old fabfile, if it exists
        _msg = "written"
        if os.path.exists(self.fabfile_name):
            _msg = "overwritten!"
        print('The file {0} will be {1}'.format(self.fabfile_name, _msg))
        try:
            os.remove(self.fabfile_name)
        except OSError:
            # The fabfile does not exist,
            # no bigie
            pass

        # Collect fabric tasks
        fabfile_tasks = '''
from fabric.api import cd, run, settings, parallel
import warnings
'''
        fabfile_all = '''
def all():
'''

        # Clean up and create new sandbox folder
        sandbox_path = os.path.join(self.project_root, self.sandbox_dir)
        _msg = "created"
        if os.path.exists(sandbox_path):
            _msg = "overwritten"
        print('The folder {0} will be {1}'.format(sandbox_path, _msg))
        try:
            shutil.rmtree(sandbox_path)
        except OSError:
            # The sandbox directory does not exist,
            # no biggie
            pass

        # Create one folder per arena layer
        # with subfolders for each casu
        os.mkdir(self.sandbox_dir)
        os.chdir(self.sandbox_dir)

        # Select particular layers
        selected_layers = self.dep.keys()
        if layer_select != 'all':
            selected_layers = [layer_select]
            if layer_select not in self.dep.keys():
                raise ValueError (
                    "[F] {} is not a layer in this deployment! aborting.".format(
                        layer_select))


        for layer in selected_layers:
            os.mkdir(layer)
            os.chdir(layer)
            for casu in self.arena[layer]:
                if layer not in self.dep or casu not in self.dep[layer]:
                    # we cannot continue with this casu since incomplete info.
                    if allow_partial is True:
                        print "[W] skipping casu {} {} since no deployment spec".format(
                            layer, casu)
                        continue
                    else:
                        # user is probably not aware of the mismatch (typo in
                        # names between files, perhaps?) Raise error.
                        raise ValueError("[F] incomplete info for casu {} (in layer {}): not specified in .dep file. Did you mean to use --allow-partial option?".format(casu, layer))

                os.mkdir(casu)
                os.chdir(casu)
                # Create the .rtc file
                with open(casu+'.rtc','a') as rtc_file:
                    yaml.dump({'name':casu}, rtc_file, default_flow_style=False)
                    yaml.dump({'pub_addr': self.arena[layer][casu]['pub_addr']},
                               rtc_file, default_flow_style=False)
                    yaml.dump({'sub_addr': self.arena[layer][casu]['sub_addr']},
                              rtc_file, default_flow_style=False)
                    yaml.dump({'msg_addr': 'tcp://*:' + self.arena[layer][casu]['msg_addr'].split(':')[-1]},
                              rtc_file, default_flow_style=False)
                    neighbors = {'neighbors':{}} # Data to be written to the .rtc
                    if self.nbg is not None:
                        sg = self.nbg.get_subgraph(layer)
                        out_neighbors = [] # Data read from the .nbg file
                        name_prefix = ''
                        if sg is None:
                            print('WARNING: No connectivity info for layer {0}'.format(layer))
                        else:
                            if sg.has_node(casu):
                                out_neighbors = sg.out_neighbors(casu)
                            elif sg.has_node(layer + '/' + casu):
                                # The CASU name is prefixed with layer name
                                name_prefix = layer + '/'
                                out_neighbors = sg.out_neighbors(name_prefix + casu)
                            else:
                                print('WARNING: No connectivity info for CASU {0}'.format(casu))
                            # Read all the neighbors and populate the .rtc
                            for nb in out_neighbors:
                                side = str(self.nbg.get_edge(name_prefix+casu,nb).attr['label'])
                                nb_full_name = str(nb).split('/')
                                nb_name = nb_full_name[-1]
                                nb_layer = layer
                                if len(nb_full_name) > 1:
                                    nb_layer = nb_full_name[0]
                                neighbors['neighbors'][side] = {'name': nb_name,
                                                                'address': self.arena[nb_layer][nb_name]['msg_addr']}

                    yaml.dump(neighbors, rtc_file, default_flow_style=False)

                # Copy the controller
                shutil.copy(os.path.join(self.project_root,self.dep[layer][casu]['controller']),'.')
                # Copy additional files
                extra = self.dep[layer][casu].get('extra',None)
                if extra:
                    for item in extra:
                        shutil.copy(os.path.join(self.project_root,item),'.')

                # compile extra args string
                _extra_args = self.dep[layer][casu].get('args', [])
                extra_args = " ".join(_extra_args)

                # Append to fabfile
                fabfile_tasks += '''
@parallel
def {task}():
    with warnings.catch_warnings():
        # ignore the CTR crypto IV warning
        warnings.filterwarnings(action="ignore", category=FutureWarning, module="Crypto", lineno=141)
        with settings(host_string='{host}', user='{username}'):
            with cd('{code_dir}'):
                run('./{command} {rtc} {extra_args}')
                                  '''.format(task=(layer+'_'+casu).replace('-','_'),
                                             host=self.dep[layer][casu]['hostname'],
                                             username=self.dep[layer][casu]['user'],
                                             code_dir=os.path.join(self.dep[layer][casu]['prefix'],layer,casu),
                                             command=os.path.basename(self.dep[layer][casu]['controller']),
                                             rtc=casu+'.rtc',
                                             extra_args=extra_args,
                                             )
                fabfile_all += '    {task}()\n'.format(task=(layer+'_'+casu).replace('-','_'))
                os.chdir('..')
            os.chdir(sandbox_path)

        os.chdir(self.project_root)

        # Finalize the fabric file
        with open(self.fabfile_name,'w') as fabfile:
            fabfile.write(fabfile_tasks)
            fabfile.write(fabfile_all)

        print('Preparation done!')
        print('Returning to original directory {0}'.format(cwd))
        os.chdir(cwd)

        self.prepared = True

    def deploy(self, layer_select='all', allow_partial=False):
        """
        Perform deployment by copying files from the sandbox directory
        to their appropriate destinations.

        arguments:
            `layer_select` : choose a single layer, or all layers to deploy to
            `allow_partial`: enable deployment specifications where the dep file
                           : specifies only a subset of the arena file's casus

        """

        if not self.prepared:
            self.prepare(layer_select=layer_select,allow_partial=allow_partial)

        cwd = os.getcwd()

        os.chdir(os.path.join(self.project_root, self.sandbox_dir))

        # Select particular layers
        selected_layers = self.dep.keys()
        if layer_select != 'all':
            selected_layers = [layer_select]
            if layer_select not in self.dep.keys():
                raise ValueError (
                    "[F] {} is not a layer in this deployment! aborting.".format(
                        layer_select))

        for layer in selected_layers:
            print('Deploying layer {0} ...'.format(layer))
            os.chdir(layer)
            for casu in self.dep[layer]:
                os.chdir(casu)
                # Connect to the target machine and deploy the files.
                with settings(host_string = self.dep[layer][casu]['hostname'],
                              user = self.dep[layer][casu]['user']):
                    destdir = os.path.join(self.dep[layer][casu]['prefix'], layer, casu)
                    run('mkdir -p ' + destdir)
                    run('rm -rf ' + os.path.join(destdir,'*'))
                    put('*', destdir)
                    # Give executable permissions to the controller
                    ctrl_name = os.path.basename(self.dep[layer][casu]['controller'])
                    run('chmod +x ' + os.path.join(destdir, ctrl_name))
                os.chdir('..')
            os.chdir('..')

        os.chdir(cwd)

def main():
    parser = argparse.ArgumentParser(description='Transfer controller code to CASUs (physical or simulated)')
    parser.add_argument('project', help='name of .assisi file specifying the project details.')
    # TODO: This is fully implemented yet!
    parser.add_argument('--layer', help='Name of single layer to deploy', default='all')
    parser.add_argument('--prepare', help='Generate rtc files, but skip transfer to target CASUs', action="store_true")
    parser.add_argument('--allow-partial',
                        help='Allow a partially specified deployment to be generated:'
                        'with a complete arena file, if only a subset of casus are '
                        'declared in the dep file, this will be permitted',
                        action='store_true')
    args = parser.parse_args()

    project = Deploy(args.project)
    with warnings.catch_warnings():
        # ignore the CTR warning in paramiko/fabric
        warnings.filterwarnings(
            action="ignore", category=FutureWarning, module="Crypto", lineno=141)

        if args.prepare is True:
            # ONLY prepare -- don't attempt any transfer
            project.prepare(args.layer, args.allow_partial)
        else:
            # the deployment stage does preparation if not already done
            project.deploy(args.layer, args.allow_partial)

if __name__ == '__main__':
    main()
