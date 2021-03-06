#!/usr/bin/env python2
# Copyright (c) 2014 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

# Base class for RPC testing

# Add python-bitcoinrpc to module search path:
import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "python-bitcoinrpc"))

import shutil
import tempfile
import traceback

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from util import *


class BitcoinTestFramework(object):

    numNodes = 4

    # These may be over-ridden by subclasses:
    def run_test(self):
        for node in self.nodes:
            assert_equal(node.getblockcount(), 200)
            assert_equal(node.getbalance(), 25*50)

    def add_options(self, parser):
        pass

    def getExtraArgs(self, n):
        """
        Provide extra args to pass to node n when starting it.  By default,
        only set -namehistory for nodes 1 and 2, so that we can test
        both cases (with history and without).  Subclasses can override
        this method to build a custom-configured network.
        """

        # We choose nodes 1 and 2 to keep -namehistory, because this allows
        # us to test both nodes with it and without it in both split
        # network parts (0/1 vs 2/3).

        if n == 1 or n == 2:
            return ["-namehistory"]

        return []

    def setup_chain(self):
        print("Initializing test directory "+self.options.tmpdir)
        extraArgs = []
        for i in range(self.numNodes):
            extraArgs.append(self.getExtraArgs(i))
        initialize_chain(self.options.tmpdir, extraArgs)

    def setup_network(self, split = False):
        extraArgs = []
        for i in range(self.numNodes):
            extraArgs.append(self.getExtraArgs(i))
        self.nodes = start_nodes(self.numNodes, self.options.tmpdir, extraArgs)

        # Connect the nodes as a "chain".  This allows us
        # to split the network between nodes 1 and 2 to get
        # two halves that can work on competing chains.

        # If we joined network halves, connect the nodes from the joint
        # on outward.  This ensures that chains are properly reorganised.
        if not split:
            connect_nodes_bi(self.nodes, 1, 2)
            sync_blocks(self.nodes[1:3])
            # Don't sync mempools (see below).

        connect_nodes_bi(self.nodes, 0, 1)
        connect_nodes_bi(self.nodes, 2, 3)
        self.is_network_split = split

        # Only sync blocks here.  The mempools might not synchronise
        # after joining a split network.
        self.sync_all('blocks')

    def split_network(self):
        """
        Split the network of four nodes into nodes 0/1 and 2/3.
        """
        assert not self.is_network_split
        stop_nodes(self.nodes)
        wait_bitcoinds()
        self.setup_network(True)

    def sync_all(self, mode = 'both'):
        modes = {'both': {'blocks': True, 'mempool': True},
                 'blocks': {'blocks': True, 'mempool': False},
                 'mempool': {'blocks': False, 'mempool': True}}
        assert mode in modes
        if self.is_network_split:
            if modes[mode]['blocks']:
                sync_blocks(self.nodes[:2])
                sync_blocks(self.nodes[2:])
            if modes[mode]['mempool']:
                sync_mempools(self.nodes[:2])
                sync_mempools(self.nodes[2:])
        else:
            if modes[mode]['blocks']:
                sync_blocks(self.nodes)
            if modes[mode]['mempool']:
                sync_mempools(self.nodes)

    def join_network(self):
        """
        Join the (previously split) network halves together.
        """
        assert self.is_network_split
        stop_nodes(self.nodes)
        wait_bitcoinds()
        self.setup_network(False)

    def main(self):
        import optparse

        parser = optparse.OptionParser(usage="%prog [options]")
        parser.add_option("--nocleanup", dest="nocleanup", default=False, action="store_true",
                          help="Leave namecoinds and test.* datadir on exit or error")
        parser.add_option("--srcdir", dest="srcdir", default="../../src",
                          help="Source directory containing namecoind/namecoin-cli (default: %default%)")
        parser.add_option("--tmpdir", dest="tmpdir", default=tempfile.mkdtemp(prefix="test"),
                          help="Root directory for datadirs")
        parser.add_option("--tracerpc", dest="trace_rpc", default=False, action="store_true",
                          help="Print out all RPC calls as they are made")
        self.add_options(parser)
        (self.options, self.args) = parser.parse_args()

        if self.options.trace_rpc:
            import logging
            logging.basicConfig(level=logging.DEBUG)

        os.environ['PATH'] = self.options.srcdir+":"+os.environ['PATH']

        check_json_precision()

        success = False
        try:
            if not os.path.isdir(self.options.tmpdir):
                os.makedirs(self.options.tmpdir)
            self.setup_chain()

            self.setup_network()

            self.run_test()

            success = True

        except JSONRPCException as e:
            print("JSONRPC error: "+e.error['message'])
            traceback.print_tb(sys.exc_info()[2])
        except AssertionError as e:
            print("Assertion failed: "+e.message)
            traceback.print_tb(sys.exc_info()[2])
        except Exception as e:
            print("Unexpected exception caught during testing: "+str(e))
            traceback.print_tb(sys.exc_info()[2])

        if not self.options.nocleanup:
            print("Cleaning up")
            stop_nodes(self.nodes)
            wait_bitcoinds()
            shutil.rmtree(self.options.tmpdir)

        if success:
            print("Tests successful")
            sys.exit(0)
        else:
            print("Failed")
            sys.exit(1)
