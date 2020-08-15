import requests
import json
import os
import base58
import PyCWaves
import time

with open('config_run.json') as json_file:
    config = json.load(json_file)

def main():
    print('reading payment file...')

    with open(config['paymentStorage']) as f:
        payments = json.load(f)

    total = 0
    for pay in payments:
        print('recipient: ' + pay['recipient'] + " amount: " + str(pay['amount'] / pow(10,8)))

        total += pay['amount']

    print('total amount to be paid: ' + str(total / pow(10,8)))

    #do actual payment
    if config['doPayment'] == 1:
        # pw = PyCWaves.PyCWaves()
        # pw.setNode(node=config['node'], chain='turtlenetwork', chain_id='L')
        # wallet = pw.Address(privateKey=config['privatekey'])

        # tx = wallet.massTransferWaves(payments,attachment='thank you for supporting mortys.node')
        # print('payment passed, txid: ' + str(tx))

        fee = 2000000 + ((len(payments) + 1) * 1000000)

        attachment = base58.b58encode(config['attachmentText'].encode('latin-1'))
        data = {
            "version": 1,
            "assetId": None,
            "sender": config['address'],
            "transfers": payments,
            "fee": fee,
            "timestamp": int(round(time.time() * 1000)),
            "type": 11,
            "attachment": attachment
        }

        paymentDone = False
        try:
            res = requests.post(config['node'] + '/assets/masstransfer', json=data, headers={'api_Key': config['apikey']}).json()

            print('payment passed, txid: ' + res['id'])
            paymentDone = True
        except Exception as e:
            print('error during payment!')
            print('failed with this transfer data: ')
            print(data)


main()