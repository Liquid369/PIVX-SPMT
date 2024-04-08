#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2017-2019 Random.Zebra (https://github.com/random-zebra/)
# Distributed under the MIT software license, see the accompanying
# file LICENSE.txt or http://www.opensource.org/licenses/mit-license.php.

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, \
    QAbstractScrollArea, QHeaderView, QLabel, QLineEdit, QFormLayout, QDoubleSpinBox, QMessageBox, \
    QApplication, QProgressBar

from constants import MINIMUM_FEE
from misc import myPopUp
from threads import ThreadFuns


class SweepAll_dlg(QDialog):
    # Dialog initialized in TabMain constructor
    def __init__(self, main_tab):
        QDialog.__init__(self, parent=main_tab.ui)
        self.main_tab = main_tab
        self.setWindowTitle('Sweep All Rewards')
        # --- Initialize Selection
        self.loading_txes = False
        self.feePerKb = MINIMUM_FEE
        self.suggestedFee = MINIMUM_FEE
        # --- Initialize GUI
        self.setupUI()
        # Connect GUI buttons
        self.connectButtons()
        # Connect Signals
        self.main_tab.caller.sig_UTXOsLoading.connect(self.update_loading_utxos)

    # Called each time before exec_ in showDialog
    def load_data(self):
        # clear table
        self.ui.tableW.setRowCount(0)
        # load last used destination from cache
        self.ui.edt_destination.setText(self.main_tab.caller.parent.cache.get("lastAddress"))
        if self.loading_txes:
            self.display_utxos()
        else:
            # Reload UTXOs
            ThreadFuns.runInThread(self.main_tab.caller.t_rewards.load_utxos_thread, ())

    def showDialog(self):
        self.load_data()
        self.exec_()

    def connectButtons(self):
        self.ui.buttonSend.clicked.connect(lambda: self.onButtonSend())
        self.ui.buttonCancel.clicked.connect(lambda: self.onButtonCancel())

    def setupUI(self):
        self.ui = Ui_SweepAllDlg()
        self.ui.setupUi(self)

    def display_utxos(self):
        required_confs = 16 if self.main_tab.caller.isTestnetRPC else 101
        rewards = self.main_tab.caller.parent.db.getRewardsList()
        self.rewardsArray = []
        for mn in [x for x in self.main_tab.caller.masternode_list if x['isHardware']]:
            x = {}
            x['name'] = mn['name']
            x['addr'] = mn['collateral'].get('address')
            x['path'] = f"{mn['hwAcc']}'/0/{mn['collateral'].get('spath')}"
            x['utxos'] = [r for r in rewards
                          if r['mn_name'] == x['name']                                       # this mn's UTXOs
                          and r['txid'] != mn['collateral'].get('txid')                      # except the collateral
                          and not (r['coinstake'] and r['confirmations'] < required_confs)]  # and immature rewards
            x['total_rewards'] = round(sum([reward['satoshis'] for reward in x['utxos']]) / 1e8, 8)
            self.rewardsArray.append(x)

        # update fee per Kb
        if self.main_tab.caller.rpcConnected:
            self.feePerKb = self.main_tab.caller.rpcClient.getFeePerKb()
            if self.feePerKb is None:
                self.feePerKb = MINIMUM_FEE
        else:
            self.feePerKb = MINIMUM_FEE

        def item(value):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.NoItemFlags)
            return item

        if len(self.rewardsArray) == 0:
            self.ui.lblMessage.setText("Unable to get raw TX from RPC server\nPlease wait for full synchronization and try again.")

        else:
            self.ui.tableW.setRowCount(len(self.rewardsArray))
            numOfInputs = 0
            for row, mnode in enumerate(self.rewardsArray):
                self.ui.tableW.setItem(row, 0, item(mnode['name']))
                self.ui.tableW.setItem(row, 1, item(mnode['addr']))
                newInputs = len(mnode['utxos'])
                numOfInputs += newInputs
                rewards_line = f"{mnode['total_rewards']} PIV"
                self.ui.tableW.setItem(row, 2, item(rewards_line))
                self.ui.tableW.setItem(row, 3, item(str(newInputs)))

            self.ui.tableW.resizeColumnsToContents()
            self.ui.lblMessage.setVisible(False)
            self.ui.tableW.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

            total = sum([float(mnode['total_rewards']) for mnode in self.rewardsArray])
            self.ui.totalLine.setText(f"<b>{round(total, 8)} PIV</b>")
            self.ui.noOfUtxosLine.setText(f"<b>{numOfInputs}</b>")

            # update fee
            estimatedTxSize = (44 + numOfInputs * 148) * 1.0 / 1000  # kB
            self.suggestedFee = round(self.feePerKb * estimatedTxSize, 8)
            self.updateFee()

    def onButtonCancel(self):
        self.AbortSend()
        self.close()

    def onButtonSend(self):
        t_rewards = self.main_tab.caller.t_rewards
        t_rewards.dest_addr = self.ui.edt_destination.text().strip()
        t_rewards.currFee = self.ui.feeLine.value() * 1e8
        # Check HW device
        while self.main_tab.caller.hwStatus != 2:
            mess = "HW device not connected. Try to connect?"
            ans = myPopUp(self.main_tab.caller, QMessageBox.Question, 'SPMT - hw check', f"{mess}")
            if ans == QMessageBox.No:
                return
            # re connect
            self.main_tab.caller.onCheckHw()
        # disable buttons (re-enabled in AbortSend)
        self.ui.buttonSend.setEnabled(False)
        self.ui.buttonCancel.setEnabled(False)
        # SEND
        t_rewards.SendRewards(self.rewardsArray, self)

    # Activated by signal sigTxabort from hwdevice
    def AbortSend(self):
        self.ui.buttonSend.setEnabled(True)
        self.ui.buttonCancel.setEnabled(True)
        self.ui.loadingLine.hide()
        self.ui.loadingLinePercent.hide()

    # Activated by signal sigTxdone from hwdevice
    def FinishSend(self, serialized_tx, amount_to_send):
        self.AbortSend()
        self.main_tab.caller.t_rewards.FinishSend_int(serialized_tx, amount_to_send)
        self.close()

    def removeSpentRewards(self):
        for mn in self.rewardsArray:
            for utxo in mn['utxos']:
                self.main_tab.caller.parent.db.deleteReward(utxo['txid'], utxo['vout'])

    def updateFee(self):
        self.ui.feeLine.setValue(self.suggestedFee)
        self.ui.feeLine.setEnabled(True)

    def update_loading_utxos(self, percent):
        if percent < 100:
            self.ui.buttonSend.setEnabled(False)
            self.ui.lblMessage.show()
            self.ui.lblMessage.setText(f"Loading rewards...{percent}%")
        else:
            self.ui.buttonSend.setEnabled(True)
            self.ui.lblMessage.hide()
            self.display_utxos()

    # Activated by signal tx_progress from hwdevice
    def updateProgressPercent(self, percent):
        if percent < 100:
            self.ui.loadingLinePercent.setValue(percent)
            self.ui.loadingLinePercent.show()
        else:
            self.ui.loadingLinePercent.hide()
        QApplication.processEvents()


class Ui_SweepAllDlg(object):
    def setupUi(self, SweepAllDlg):
        SweepAllDlg.setModal(True)
        layout = QVBoxLayout(SweepAllDlg)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("<b><i>Sweep Rewards From All Masternodes</i></b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        self.lblMessage = QLabel(SweepAllDlg)
        self.lblMessage.setText("Loading rewards...")
        self.lblMessage.setWordWrap(True)
        layout.addWidget(self.lblMessage)
        self.tableW = QTableWidget(SweepAllDlg)
        self.tableW.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.tableW.setShowGrid(True)
        self.tableW.setColumnCount(4)
        self.tableW.setRowCount(0)
        self.tableW.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableW.verticalHeader().hide()
        item = QTableWidgetItem()
        item.setText("Name")
        item.setTextAlignment(Qt.AlignCenter)
        self.tableW.setHorizontalHeaderItem(0, item)
        item = QTableWidgetItem()
        item.setText("Address")
        item.setTextAlignment(Qt.AlignCenter)
        self.tableW.setHorizontalHeaderItem(1, item)
        item = QTableWidgetItem()
        item.setText("Rewards")
        item.setTextAlignment(Qt.AlignCenter)
        self.tableW.setHorizontalHeaderItem(2, item)
        item = QTableWidgetItem()
        item.setText("n. of UTXOs")
        item.setTextAlignment(Qt.AlignCenter)
        self.tableW.setHorizontalHeaderItem(3, item)
        layout.addWidget(self.tableW)
        myForm = QFormLayout()
        myForm.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        hBox = QHBoxLayout()
        self.totalLine = QLabel("<b>0 PIV</b>")
        hBox.addWidget(self.totalLine)
        self.loadingLine = QLabel("<b style='color:red'>Preparing TX.</b> Completed: ")
        self.loadingLinePercent = QProgressBar()
        self.loadingLinePercent.setMaximumWidth(200)
        self.loadingLinePercent.setMaximumHeight(15)
        self.loadingLinePercent.setRange(0, 100)
        hBox.addWidget(self.loadingLine)
        hBox.addWidget(self.loadingLinePercent)
        self.loadingLine.hide()
        self.loadingLinePercent.hide()
        myForm.addRow(QLabel("Total Rewards: "), hBox)
        self.noOfUtxosLine = QLabel("<b>0</b>")
        myForm.addRow(QLabel("Total number of UTXOs: "), self.noOfUtxosLine)
        hBox = QHBoxLayout()
        self.edt_destination = QLineEdit()
        self.edt_destination.setToolTip("PIVX address to transfer rewards to")
        hBox.addWidget(self.edt_destination)
        hBox.addWidget(QLabel("Fee"))
        self.feeLine = QDoubleSpinBox()
        self.feeLine.setDecimals(8)
        self.feeLine.setPrefix("PIV  ")
        self.feeLine.setToolTip("Insert a small fee amount")
        self.feeLine.setFixedWidth(120)
        self.feeLine.setSingleStep(0.001)
        hBox.addWidget(self.feeLine)
        myForm.addRow(QLabel("Destination Address"), hBox)
        layout.addLayout(myForm)
        hBox = QHBoxLayout()
        self.buttonCancel = QPushButton("Cancel")
        hBox.addWidget(self.buttonCancel)
        self.buttonSend = QPushButton("Send")
        hBox.addWidget(self.buttonSend)
        layout.addLayout(hBox)
        SweepAllDlg.resize(700, 300)
