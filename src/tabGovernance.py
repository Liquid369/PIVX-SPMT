#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os.path
from PyQt5.Qt import QFont, QDesktopServices, QUrl
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QTableWidgetItem, QPushButton, QWidget, QHBoxLayout,\
    QMessageBox

from qt.gui_tabGovernance import TabGovernance_gui
from qt.dlg_proposalDetails import ProposalDetails_dlg
from qt.dlg_selectMNs import SelectMNs_dlg
from qt.dlg_budgetProjection import BudgetProjection_dlg
from misc import printException, getCallerName, getFunctionName, printDbg, printOK
from threads import ThreadFuns
import time
from utils import ecdsa_sign


class Proposal():
    def __init__(self, name, URL, Hash, FeeHash, BlockStart, BlockEnd, TotalPayCount, RemainingPayCount, 
                 PayMentAddress, Yeas, Nays, Abstains, TotalPayment, MonthlyPayment):
        self.name = name
        self.URL = URL if URL.startswith('http') or URL.startswith('https') else 'http://'+URL
        self.Hash = Hash
        self.FeeHash = FeeHash
        self.BlockStart = int(BlockStart)
        self.BlockEnd = int(BlockEnd)
        self.TotalPayCount = int(TotalPayCount)
        self.RemainingPayCount = int(RemainingPayCount)
        self.PaymentAddress = PayMentAddress        
        self.Yeas = int(Yeas)
        self.Nays = int(Nays)
        self.Abstains = int(Abstains)
        self.ToalPayment = TotalPayment
        self.MonthlyPayment = MonthlyPayment
        ## list of personal masternodes voting
        self.MyYeas = []
        self.MyAbstains = []
        self.MyNays = []
        

class TabGovernance():
    def __init__(self, caller):
        self.caller = caller
        self.proposals = []  # list of Proposal Objects
        self.selectedProposals = []
        self.votingMasternodes = self.caller.parent.cache.get("votingMasternodes")
        self.successVotes = 0
        self.failedVotes = 0
        ##--- Initialize GUI
        self.ui = TabGovernance_gui(caller)
        self.updateSelectedMNlabel()
        self.caller.tabGovernance = self.ui
        # Connect GUI buttons
        self.vote_codes = ["abstains", "yes", "no"]
        self.ui.refreshProposals_btn.clicked.connect(lambda: self.onRefreshProposals())
        self.ui.selectMN_btn.clicked.connect(lambda:  SelectMNs_dlg(self).exec_())
        self.ui.budgetProjection_btn.clicked.connect(lambda:  BudgetProjection_dlg(self).exec_())
        self.ui.proposalBox.itemClicked.connect(lambda: self.updateSelection())
        self.ui.voteYes_btn.clicked.connect(lambda: self.onVote(1))
        self.ui.voteAbstain_btn.clicked.connect(lambda: self.onVote(0))
        self.ui.voteNo_btn.clicked.connect(lambda: self.onVote(2))
        
            
    def countMyVotes(self):
        for prop in self.proposals:
            mnList = self.caller.masternode_list
            budgetVotes = self.caller.rpcClient.getBudgetVotes(prop.name)
            budgetYeas = [x['mnId'] for x in budgetVotes if x['Vote'] == "YES"]
            budgetAbstains = [x['mnId'] for x in budgetVotes if x['Vote'] == "ABSTAIN"]
            budgetNays = [x['mnId'] for x in budgetVotes if x['Vote'] == "NO"]
            prop.MyYeas = [mn['name'] for mn in mnList if mn['collateral'].get('txid') in budgetYeas]
            prop.MyAbstains = [mn['name'] for mn in mnList if mn['collateral'].get('txid') in budgetAbstains]
            prop.MyNays = [mn['name'] for mn in mnList if mn['collateral'].get('txid') in budgetNays]
        
    def displayProposals(self):
        if len(self.proposals) == 0:
            return
        
        def item(value):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            return item
        
        def itemButton(value, icon_num):
            pwidget = QWidget()
            btn = QPushButton()
            if icon_num == 0:
                btn.setIcon(self.ui.link_icon)
                btn.setToolTip("Open WebPage: %s" % str(value))
                btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(str(value))))
            else:
                btn.setIcon(self.ui.search_icon)
                btn.setToolTip("Check proposal details...")
                btn.clicked.connect(lambda: ProposalDetails_dlg(self.ui, value).exec_())
            
            pLayout = QHBoxLayout()
            pLayout.addWidget(btn)
            pLayout.setContentsMargins(0, 0, 0, 0)
            pwidget.setLayout(pLayout)
            return pwidget
        
        self.ui.mnCountLabel.setText("Total MN Count: <em>%d</em>" % self.mnCount)
        self.ui.proposalBox.setRowCount(len(self.proposals))
        
        for row, prop in enumerate(self.proposals):
            self.ui.proposalBox.setItem(row, 0, item(prop.name))
            self.ui.proposalBox.item(row, 0).setFont(QFont("Arial", 9, QFont.Bold))
            
            hash = item(prop.Hash)
            hash.setToolTip(prop.Hash)
            self.ui.proposalBox.setItem(row, 1, hash)
            
            self.ui.proposalBox.setCellWidget(row, 2, itemButton(prop.URL, 0))
            
            monthlyPay = item(prop.MonthlyPayment)
            monthlyPay.setData(Qt.EditRole, int(round(prop.MonthlyPayment)))
            self.ui.proposalBox.setItem(row, 3, monthlyPay)
            
            payments = "%d / %d" % (prop.RemainingPayCount, prop.TotalPayCount)
            self.ui.proposalBox.setItem(row, 4, item(payments))
            
            net_votes = "%d / %d / %d" % (prop.Yeas, prop.Abstains, prop.Nays)
            votes = item(net_votes)
            if (prop.Yeas - prop.Nays) > 0.1 * self.mnCount:
                votes.setBackground(Qt.green)
            if (prop.Yeas - prop.Nays) < 0:
                votes.setBackground(Qt.red)
            if prop.RemainingPayCount == 0:
                votes.setBackground(Qt.yellow)
            self.ui.proposalBox.setItem(row, 5, votes)
            
            my_votes = "%d / %d / %d" % (len(prop.MyYeas), len(prop.MyAbstains), len(prop.MyNays))
            self.ui.proposalBox.setItem(row, 6, item(my_votes))
            self.ui.proposalBox.setCellWidget(row, 7, itemButton(prop, 1))
            
        # Sort by Monthly Price descending
        self.ui.proposalBox.setSortingEnabled(True)
        self.ui.proposalBox.sortByColumn(3, Qt.DescendingOrder)
        
            
    
    
    def getSelection(self):
        items = self.ui.proposalBox.selectedItems()
        # Save row indexes to a set to avoid repetition
        rows = set()
        for i in range(0, len(items)):
            row = items[i].row()
            rows.add(row)
        rowsList = list(rows)
        hashesList = [self.ui.proposalBox.item(row,1).text() for row in rowsList]
        #print("Selected: " + str([p.name for p in self.proposals if p.name in namesList]))
        return [p for p in self.proposals if p.Hash in hashesList]
            
     
            
    @pyqtSlot()
    def onRefreshProposals(self):
        self.ui.proposalBox.setRowCount(0)
        self.proposals = []
        self.selectedProposals = []
        self.ui.proposalBox.setSortingEnabled(False)
        ThreadFuns.runInThread(self.loadProposals_thread, (), self.displayProposals)
        
        
    @pyqtSlot(str)
    def onVote(self, vote_code):
        ThreadFuns.runInThread(self.vote_thread, ([vote_code]), self.vote_thread_end)
    
    
    @pyqtSlot(object) 
    def loadProposals_thread(self, ctrl):
        if not self.caller.rpcConnected:
            printException(getCallerName(), getFunctionName(), "RPC server not connected", "")
            return
        
        self.proposals = self.caller.rpcClient.getProposals()
        num_of_masternodes = self.caller.rpcClient.getMasternodeCount()

        if num_of_masternodes is None:
            printDbg("Total number of masternodes not available. Background coloring not accurate")
            self.mnCount = 1
        else:
            self.mnCount = num_of_masternodes.get("total")  
        
        self.countMyVotes()
        
        
    def updateSelectedMNlabel(self):
        selected_MN = len(self.votingMasternodes)
        if selected_MN == 1:
            label = "<em><b>1</b> masternode selected for voting</em>"
        else:
            label = "<em><b>%d</b> masternodes selected for voting</em>" % selected_MN
        self.ui.selectedMNlabel.setText(label)
        
        
    def updateSelection(self):
        self.selectedProposals = self.getSelection()
        if len(self.selectedProposals) == 1:
            self.ui.selectedPropLabel.setText("<em><b>1</b> proposal selected")
        else:
            self.ui.selectedPropLabel.setText("<em><b>%d</b> proposals selected" % len(self.selectedProposals))
            
            
    
    @pyqtSlot(object, str)
    def vote_thread(self, ctrl, vote_code):
        # vote_code in ["yes", "abstain", "no"]
        self.successVotes = 0
        self.failedVotes = 0
        for prop in self.selectedProposals:
            for mn in self.votingMasternodes:
                mess = "Processing '%s' vote on behalf of masternode [%s]" % (self.vote_codes[vote_code], mn[1])
                mess += " for the proposal {%s}" % prop.name
                printDbg(mess)
                
                vote_sig = ''
                serialize_for_sig = ''
                sig_time = int(time.time())

                try:
                    # Get mnPrivKey
                    currNode = next(x for x in self.caller.masternode_list if x['name']==mn[1])
                    if currNode is None:
                        raise Exception("currNode not found for current voting masternode %s" % mn[1])
                    mnPrivKey = currNode['mnPrivKey']
                    
                    serialize_for_sig = mn[0][:64] + '-' + str(currNode['collateral'].get('txidn')) + prop.Hash + str(vote_code) + str(sig_time)                  
                    
                    # Sign vote
                    vote_sig = ecdsa_sign(serialize_for_sig, mnPrivKey)
                    
                    # Broadcast the vote
                    v_res = self.caller.rpcClient.mnBudgetRawVote(
                        mn_tx_hash=currNode['collateral'].get('txid'),
                        mn_tx_index=int(currNode['collateral'].get('txidn')),
                        proposal_hash=prop.Hash,
                        vote=self.vote_codes[vote_code],
                        time=sig_time,
                        vote_sig=vote_sig)
                    
                    printOK(v_res)
                    
                    if v_res == 'Voted successfully':
                        self.successVotes += 1
                    else:
                        self.failedVotes += 1
                    
                except Exception as e:
                    err_msg = "Exception in vote_thread"
                    printException(getCallerName(), getFunctionName(), err_msg, e.args)



    def vote_thread_end(self):
        message = '<p>Votes sent</p>'
        if self.successVotes > 0:
            message += '<p>Successful Votes: <b>%d</b></p>' % self.successVotes
        if self.failedVotes > 0:
            message += '<p>Failed Votes: <b>%d</b>' % self.failedVotes
        self.caller.myPopUp2(QMessageBox.Information, 'Vote Finished', message)
                                        
                    