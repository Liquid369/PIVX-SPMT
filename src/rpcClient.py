#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
import threading

from PyQt5.QtCore import pyqtSlot, QSettings

from constants import DEFAULT_PROTOCOL_VERSION, MINIMUM_FEE
from misc import getCallerName, getFunctionName, printException, printDbg, now
from tabGovernance import Proposal


class RpcClient:
        
    def __init__(self, rpc_protocol, rpc_host, rpc_user, rpc_password):
        # Lock for threads
        self.lock = threading.Lock()

        rpc_url = "%s://%s:%s@%s" % (rpc_protocol, rpc_user, rpc_password, rpc_host)

        try:
            self.lock.acquire()
            self.conn = AuthServiceProxy(rpc_url, timeout=30)     
        except JSONRPCException as e:
            err_msg = 'remote or local PIVX-cli running?'
            printException(getCallerName(), getFunctionName(), err_msg, e)
        except Exception as e:
            err_msg = 'remote or local PIVX-cli running?'
            printException(getCallerName(), getFunctionName(), err_msg, e)
        finally:
            self.lock.release()
    
    
    
    def decodeRawTransaction(self, rawTx):
        try:
            self.lock.acquire()
            res = self.conn.decoderawtransaction(rawTx)    
        except Exception as e:
            err_msg = 'error in decodeRawTransaction'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = None
        finally:
            self.lock.release()
        
        return res
    
    
    
    def getAddressUtxos(self, addresses):
        try:
            self.lock.acquire()
            res = self.conn.getaddressutxos({'addresses': addresses})    
        except Exception as e:
            err_msg = "error in getAddressUtxos"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = None
        finally:
            self.lock.release()
        
        return res
    
    
    
    
    def getBlockCount(self):
        try:
            self.lock.acquire()
            n = self.conn.getblockcount()
        except Exception as e:
            err_msg = 'remote or local PIVX-cli running?'
            if str(e.args[0]) != "Request-sent":
                printException(getCallerName(), getFunctionName(), err_msg, e.args)
            n = 0
        finally:
            self.lock.release()
            
        return n
    
    
    
    
    def getBlockHash(self, blockNum):
        try:
            self.lock.acquire()
            h = self.conn.getblockhash(blockNum)
        except Exception as e:
            err_msg = 'remote or local PIVX-cli running?'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            h = None
        finally:
            self.lock.release()
            
        return h
    
    
    def getBudgetVotes(self, proposal):
        try:
            self.lock.acquire()
            votes = self.conn.getbudgetvotes(proposal)
        except Exception as e:
            err_msg = 'remote or local PIVX-cli running?'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            votes = {}
        finally:
            self.lock.release()
            
        return votes
    
    
    def getFeePerKb(self):
        try:
            self.lock.acquire()
            # get transaction data from last 200 blocks
            feePerKb = float(self.conn.getfeeinfo(200)['feeperkb'])
            res = (feePerKb if feePerKb > MINIMUM_FEE else MINIMUM_FEE)
        except Exception as e:
            err_msg = 'error in getFeePerKb'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = MINIMUM_FEE
        finally:
            self.lock.release()
            
        return res
    
    
    
    def getMNStatus(self, address):
        try:
            self.lock.acquire()
            mnStatusList = self.conn.listmasternodes(address)
            if not mnStatusList:
                return None
            mnStatus = mnStatusList[0]
            mnStatus['mnCount'] = self.conn.getmasternodecount()['enabled']
        except Exception as e:
            err_msg = "error in getMNStatus"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            mnStatus = None
        finally:
            self.lock.release()
            
        return mnStatus
                
                

    def getMasternodeCount(self):
        try:
            self.lock.acquire()
            ans = self.conn.getmasternodecount()
        except Exception as e:
            err_msg = "error in getMasternodeCount"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            ans = None
        finally:
            self.lock.release()
            
        return ans
                
                
    def getMasternodes(self):
        mnList = {}
        mnList['last_update'] = now()
        score = []
        try:
            self.lock.acquire()
            masternodes = self.conn.listmasternodes()
        except Exception as e:
            err_msg = "error in getMasternodes"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            masternodes = []
        finally:
            self.lock.release()
        
        for mn in masternodes:
            
            if mn.get('status') == 'ENABLED':
                if mn.get('lastpaid') == 0:
                    mn['score'] = mn.get('activetime')
                else:
                    lastpaid_ago = now() - mn.get('lastpaid')
                    mn['score'] = min(lastpaid_ago, mn.get('activetime'))
                
            else:
                mn['score'] = 0
                
            score.append(mn)
        
        score.sort(key=lambda x: x['score'], reverse=True)
        
        for mn in masternodes:
            mn['queue_pos'] = score.index(mn)
                
        mnList['masternodes'] = masternodes
                
        return mnList
    
    
    
    def getNextSuperBlock(self):
        try:
            self.lock.acquire()
            n = self.conn.getnextsuperblock()
        except Exception as e:
            err_msg = 'remote or local PIVX-cli running?'
            if str(e.args[0]) != "Request-sent":
                printException(getCallerName(), getFunctionName(), err_msg, e.args)
            n = 0
        finally:
            self.lock.release()
            
        return n    
    
    
    
    def getProposals(self):
        proposals = []
        try:
            self.lock.acquire()
            data = self.conn.getbudgetinfo()
        except Exception as e:
            err_msg = "error getting proposals"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            data = []
        finally:
            self.lock.release()
            
        for p in data:
            new_proposal = Proposal(p.get('Name'), p.get('URL'), p.get('Hash'), p.get('FeeHash'), p.get('BlockStart'), 
                                    p.get('BlockEnd'), p.get('TotalPaymentCount'), p.get('RemainingPaymentCount'), p.get('PaymentAddress'), 
                                    p.get('Yeas'), p.get('Nays'), p.get('Abstains'), 
                                    float(p.get('TotalPayment')), float(p.get('MonthlyPayment')))
            proposals.append(new_proposal)
            
        return proposals
    
    
    
    def getProposalsProjection(self):
        proposals = []
        try:
            self.lock.acquire()
            data = self.conn.getbudgetprojection()
        except Exception as e:
            err_msg = "error getting proposals projection"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            data = []
        finally:
            self.lock.release()
            
        for p in data:
            new_proposal = Proposal(p.get('Name'), p.get('URL'), p.get('Hash'), p.get('FeeHash'), p.get('BlockStart'), 
                                    p.get('BlockEnd'), p.get('TotalPaymentCount'), p.get('RemainingPaymentCount'), p.get('PaymentAddress'), 
                                    p.get('Yeas'), p.get('Nays'), p.get('Abstains'), p.get('TotalPayment'), p.get('MonthlyPayment'))
            new_proposal = {}
            new_proposal['Name'] = p.get('Name')
            new_proposal['Allotted'] = float(p.get("Alloted"))
            new_proposal['Votes'] = p.get('Yeas') - p.get('Nays')
            new_proposal['Total_Allotted'] = float(p.get('TotalBudgetAlloted'))
            proposals.append(new_proposal)
            
        return proposals
    
    
    
    
    def getProtocolVersion(self):
        try:
            self.lock.acquire()
            prot_version = self.conn.getinfo().get('protocolversion')
            res = int(prot_version)      
        except Exception as e:
            err_msg = 'error in getProtocolVersion'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = DEFAULT_PROTOCOL_VERSION
        finally:
            self.lock.release()
        
        return res    
     
            
    
    
    def getRawTransaction(self, txid):
        try:
            self.lock.acquire()
            res = self.conn.getrawtransaction(txid)
        except Exception as e:
            err_msg = "is Blockchain synced?"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = None
        finally:
            self.lock.release()
            
        return res
    
    
    
    
    def getStatus(self):
        status = False
        statusMess = "Unable to connect to a PIVX RPC server.\n" 
        statusMess += "Either the local PIVX wallet is not open, or the remote RPC server is not responding."
        n = 0
        try:
            self.lock.acquire()
            n = self.conn.getblockcount()
            if n > 0:
                status = True
                statusMess = "Connected to PIVX Blockchain"
                
        except Exception as e:
            # If loading block index set lastBlock=1
            if str(e.args[0]) == "Loading block index..." or str(e.args[0]) == "Verifying blocks...":
                printDbg(str(e.args[0]))
                statusMess = "PIVX wallet is connected but still synchronizing / verifying blocks"
                n = 1
            elif str(e.args[0]) == "Remote end closed connection without response":
                # try again
                statusMess = "Remote end closed connection without response"                
            elif str(e.args[0]) != "Request-sent" and str(e.args[0]) != "10061":
                err_msg = "Error while contacting RPC server"
                printException(getCallerName(), getFunctionName(), err_msg, e.args)

                
        finally:
            self.lock.release()
                
        return status, statusMess, n
     
    
    
    
    def isBlockchainSynced(self):
        try:
            self.lock.acquire()
            res = self.conn.mnsync('status').get("IsBlockchainSynced")
        except Exception as e:
            if str(e.args[0]) != "Request-sent":
                err_msg = "error in isBlockchainSynced"
                printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = False
        finally:
            self.lock.release()
        
        return res
    
    
    
    def mnBudgetRawVote(self, mn_tx_hash, mn_tx_index, proposal_hash, vote, time, vote_sig):
        try:
            self.lock.acquire()
            res = self.conn.mnbudgetrawvote(mn_tx_hash, mn_tx_index, proposal_hash, vote, time, vote_sig)
        except Exception as e:
            err_msg = "error in mnBudgetRawVote"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = None
        finally:
            self.lock.release()
        
        return res   
            
            
    def decodemasternodebroadcast(self, work):
        try:
            self.lock.acquire()
            res = self.conn.decodemasternodebroadcast(work.strip())
        except Exception as e:
            err_msg = "error in decodemasternodebroadcast"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = ""
        finally:
            self.lock.release()
        
        return res
    
            
    
    def relaymasternodebroadcast(self, work):
        try:
            self.lock.acquire()
            res = self.conn.relaymasternodebroadcast(work.strip())
        except Exception as e:
            err_msg = "error in relaymasternodebroadcast"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)    
            res = ""
        finally:
            self.lock.release()
        
        return res
    


    def sendRawTransaction(self, tx_hex, use_swiftx):
        try:
            self.lock.acquire()
            tx_id = self.conn.sendrawtransaction(tx_hex, True, bool(use_swiftx))
        except Exception as e:
            err_msg = 'error in rpcClient.sendRawTransaction'
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            tx_id = None
        finally:
            self.lock.release()
        
        return tx_id
    
    
    
    
    def verifyMessage(self, pivxaddress, signature, message):
        try:
            self.lock.acquire()
            res = self.conn.verifymessage(pivxaddress, signature, message)
        except Exception as e:
            err_msg = "error in verifyMessage"
            printException(getCallerName(), getFunctionName(), err_msg, e.args)
            res = False
        finally:
            self.lock.release()
            
        return res
            