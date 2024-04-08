#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2017 chaeplin
# Copyright (c) 2017 Bertrand256
# Copyright (c) 2017-2019 Random.Zebra (https://github.com/random-zebra/)
# Distributed under the MIT software license, see the accompanying
# file LICENSE.txt or http://www.opensource.org/licenses/mit-license.php.

import base64
from bitcoin import bin_hash160, b58check_to_hex, ecdsa_raw_sign, ecdsa_raw_verify, privkey_to_pubkey, \
    encode_sig, decode_sig, dbl_sha256, bin_dbl_sha256, ecdsa_raw_recover, encode_pubkey
from ipaddress import ip_address

from misc import getCallerName, getFunctionName, printException
from pivx_b58 import b58decode
from pivx_hashlib import wif_to_privkey, pubkey_to_address

# Bitcoin opcodes used in the application
OP_DUP = b'\x76'
OP_HASH160 = b'\xA9'
OP_EQUALVERIFY = b'\x88'
OP_CHECKSIG = b'\xAC'
OP_EQUAL = b'\x87'
OP_RETURN = b'\x6a'
OP_CHECKCOLDSTAKEVERIFY = b'\xD1'
OP_ROT = b'\x7B'
# Prefixes - Check P2SH
P2PKH_PREFIXES = ['D']
P2SH_PREFIXES = ['7']
P2PKH_PREFIXES_TNET = ['x', 'y']
P2SH_PREFIXES_TNET = ['8', '9']


def b64encode(text):
    return base64.b64encode(bytearray.fromhex(text)).decode('utf-8')


def checkPivxAddr(address, isTestnet=False):
    try:
        # check leading char 'D' or (for testnet) 'x' or 'y'
        if isTestnet and address[0] not in P2PKH_PREFIXES_TNET + P2SH_PREFIXES_TNET:
            return False
        if not isTestnet and address[0] not in P2PKH_PREFIXES + P2SH_PREFIXES:
            return False

        # decode and verify checksum
        addr_bin = bytes.fromhex(b58decode(address).hex())
        addr_bin_check = bin_dbl_sha256(addr_bin[0:-4])[0:4]
        if addr_bin[-4:] != addr_bin_check:
            return False

        return True
    except Exception:
        return False


def compose_tx_locking_script(dest_address, isTestnet):
    """
    Create a Locking script (ScriptPubKey) that will be assigned to a transaction output.
    :param dest_address: destination address in Base58Check format
    :return: sequence of opcodes and its arguments, defining logic of the locking script
    """
    pubkey_hash = bytearray.fromhex(b58check_to_hex(dest_address))  # convert address to a public key hash
    if len(pubkey_hash) != 20:
        raise Exception(f'Invalid length of the public key hash: {len(pubkey_hash)}')

    if (((not isTestnet) and (dest_address[0] in P2PKH_PREFIXES))
            or (isTestnet and (dest_address[0] in P2PKH_PREFIXES_TNET))):
        # sequence of opcodes/arguments for p2pkh (pay-to-public-key-hash)
        scr = OP_DUP + \
              OP_HASH160 + \
              int.to_bytes(len(pubkey_hash), 1, byteorder='little') + \
              pubkey_hash + \
              OP_EQUALVERIFY + \
              OP_CHECKSIG
    elif (((not isTestnet) and (dest_address[0] in P2SH_PREFIXES))
          or (isTestnet and (dest_address[0] in P2SH_PREFIXES_TNET))):
        # sequence of opcodes/arguments for p2sh (pay-to-script-hash)
        scr = OP_HASH160 + \
              int.to_bytes(len(pubkey_hash), 1, byteorder='little') + \
              pubkey_hash + \
              OP_EQUAL
    else:
        mess = f'Invalid dest address prefix: {dest_address[0]}'
        if isTestnet:
            mess += ' for testnet'
        raise Exception(mess)
    return scr


def compose_tx_locking_script_OR(message):
    """
    Create a Locking script (ScriptPubKey) that will be assigned to a transaction output.
    :param message: data for the OP_RETURN
    :return: sequence of opcodes and its arguments, defining logic of the locking script
    """
    data = message.encode()
    scr = OP_RETURN + int.to_bytes(len(data), 1, byteorder='little') + data

    return scr


def ecdsa_sign(msg, priv):
    return ecdsa_sign_bin(electrum_sig_hash(msg), priv)


def ecdsa_verify_addr(msg, sig, addr):
    isTestnet = addr[0] not in P2PKH_PREFIXES
    if not checkPivxAddr(addr, isTestnet):
        return False
    v, r, s = decode_sig(sig)
    Q = ecdsa_raw_recover(electrum_sig_hash(msg), (v, r, s))
    Qenc = encode_pubkey(Q, 'hex_compressed') if v >= 31 else encode_pubkey(Q, 'hex')

    return pubkey_to_address(Qenc, isTestnet) == addr


def electrum_sig_hash(message):
    """
    Based on project: https://github.com/chaeplin/dashmnb.
    """
    padded = b'\x18DarkNet Signed Message:\n' + num_to_varint(len(message)) + from_string_to_bytes(message)
    return dbl_sha256(padded)


def ecdsa_sign_bin(msgbin, priv):
    v, r, s = ecdsa_raw_sign(msgbin, priv)
    sig = encode_sig(v, r, s)
    pubkey = privkey_to_pubkey(wif_to_privkey(priv))

    ok = ecdsa_raw_verify(msgbin, decode_sig(sig), pubkey)
    if not ok:
        raise Exception('Bad signature!')
    return sig


def extract_pkh_from_locking_script(script):
    if len(script) == 25:
        if script[0:1] == OP_DUP and script[1:2] == OP_HASH160:
            if read_varint(script, 2)[0] == 20:
                return script[3:23]
            else:
                raise Exception('Non-standard public key hash length (should be 20)')

    elif len(script) == 35:
        scriptlen = read_varint(script, 0)[0]
        if scriptlen in [32, 33]:
            return bin_hash160(script[1:1 + scriptlen])
        else:
            raise Exception('Non-standard public key length (should be 32 or 33)')

    elif IsPayToColdStaking(script):
        return script[28:48]
    raise Exception(f'Non-standard locking script type (should be P2PKH or P2PK). len is {len(script)}')


def IsPayToColdStaking(script):
    return (len(script) == 51 and
            script[2] == int.from_bytes(OP_ROT, 'little') and
            script[4] == int.from_bytes(OP_CHECKCOLDSTAKEVERIFY, 'little') and
            script[5] == 20 and
            script[27] == 20 and
            script[49] == int.from_bytes(OP_EQUALVERIFY, 'little') and
            script[50] == int.from_bytes(OP_CHECKSIG, 'little'))


def GetDelegatedStaker(script):
    return script[6:26]


def from_string_to_bytes(a):
    return a if isinstance(a, bytes) else bytes(a, 'utf-8')


def ipmap(ip, port):
    try:
        ipv6map = ''

        if len(ip) == 62 and ip.endswith('.onion'):
            vchOnionPrefix = bytes([0x04, 32])
            vchAddr = base64.b32decode(ip[0:-6], True)
            vchAddrBytes = vchOnionPrefix + vchAddr[:32]
            if len(vchAddr) != 35 and vchAddr[-1] != b'\x03':
                raise Exception(f'Invalid TorV3 address {ip}')
            return vchAddrBytes.hex() + int(port).to_bytes(2, byteorder='big').hex()

        ipAddr = ip_address(ip)

        if ipAddr.version == 4:
            ipv6map = '00000000000000000000ffff'
            ip_digits = map(int, ipAddr.exploded.split('.'))
            for i in ip_digits:
                ipv6map += i.to_bytes(1, byteorder='big')[::-1].hex()

        elif ipAddr.version == 6:
            ip_hextets = map(str, ipAddr.exploded.split(':'))
            for a in ip_hextets:
                ipv6map += a

        else:
            raise Exception(f"invalid version number ({ipAddr.version})")

        ipv6map += int(port).to_bytes(2, byteorder='big').hex()
        if len(ipv6map) != 36:
            raise Exception(f"Problems! len is {len(ipv6map)}")
        return ipv6map

    except Exception as e:
        err_msg = f"error in ipmap"
        printException(f"{getCallerName()}", f"{getFunctionName()}", f"{err_msg}", f"{e.args}")


def num_to_varint(a):
    """
    Based on project: https://github.com/chaeplin/dashmnb
    """
    x = int(a)
    if x < 253:
        return x.to_bytes(1, byteorder='big')
    elif x < 65536:
        return int(253).to_bytes(1, byteorder='big') + x.to_bytes(2, byteorder='little')
    elif x < 4294967296:
        return int(254).to_bytes(1, byteorder='big') + x.to_bytes(4, byteorder='little')
    else:
        return int(255).to_bytes(1, byteorder='big') + x.to_bytes(8, byteorder='little')


def read_varint(buffer, offset):
    if (buffer[offset] < 0xfd):
        value_size = 1
        value = buffer[offset]
    elif (buffer[offset] == 0xfd):
        value_size = 3
        value = int.from_bytes(buffer[offset + 1: offset + 3], byteorder='little')
    elif (buffer[offset] == 0xfe):
        value_size = 5
        value = int.from_bytes(buffer[offset + 1: offset + 5], byteorder='little')
    elif (buffer[offset] == 0xff):
        value_size = 9
        value = int.from_bytes(buffer[offset + 1: offset + 9], byteorder='little')
    else:
        raise Exception("Invalid varint size")
    return value, value_size


def serialize_input_str(tx, prevout_n, sequence, script_sig):
    """
    Based on project: https://github.com/chaeplin/dashmnb.
    """
    s = ['CTxIn(']
    s.append(f'COutPoint({tx}, {prevout_n})')
    s.append(', ')
    if tx == '00' * 32 and prevout_n == 0xffffffff:
        s.append(f'coinbase {script_sig}')

    else:
        script_sig2 = script_sig
        if len(script_sig2) > 24:
            script_sig2 = script_sig2[0:24]
        s.append(f'scriptSig={script_sig2}')

    if sequence != 0xffffffff:
        s.append(f', nSequence={sequence}')

    s.append(')')
    return ''.join(s)
