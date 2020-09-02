import requests
import hyperjson
import os

myLeases = {}
myCanceledLeases = {}
myForgedBlocks = []
payments = {}
totalfee = 0

with open('config_run.json') as json_file:
    config = hyperjson.load(json_file)

    
def cleanBlocks(blocksJSON):
    for block in blocksJSON:
        
        if 'totalFee' in block:
            block['fee'] = block['totalFee']

        block.pop('nxt-consensus', None)
        block.pop('version', None)
        block.pop('features', None)
        block.pop('blocksize', None)
        block.pop('signature', None)
        block.pop('reference', None)
        block.pop('transactionCount', None)
        block.pop('generatorPublicKey', None)
        block.pop('desiredReward', None)
        block.pop('timestamp', None)

        block['transactions'] = [transaction for transaction in block['transactions'] if
                                 transaction['type'] == 8 or transaction['type'] == 9]

    return blocksJSON


def getAllBlocks():
    startblock = config['firstBlock']
    steps = 100
    blocks = []
    
    #determine endBlock
    if config['endBlock'] == 0:
        endBlock = requests.get(config['node'] + '/blocks/height').json()['height'] - 1
    else:
        endBlock = config['endBlock']

    #try to load previous processed blocks
    try:
        with open(config['blockStorage'], 'r') as f:
            blocks = hyperjson.load(f)

        startblock = blocks[len(blocks) - 1]['height'] + 1
        print('retrieved blocks from ' + str(blocks[0]['height']) + ' to ' + str(startblock - 1))
    except Exception as e:
        print('no previous blocks file found')

    #retrieve blocks
    while (startblock < endBlock):
        if (startblock + (steps - 1) < endBlock):
            print('getting blocks from ' + str(startblock) + ' to ' + str(startblock + (steps - 1)))
            blocksJSON = requests.get(config['node'] + '/blocks/seq/' + str(startblock) + '/' + str(startblock + (steps - 1))).json()
        else:
            print('getting blocks from ' + str(startblock) + ' to ' + str(endBlock))
            blocksJSON = requests.get(config['node'] + '/blocks/seq/' + str(startblock) + '/' + str(endBlock)).json()

        #clear payed tx
        if (startblock + (steps - 1)) < config['startBlock']:
            for block in blocksJSON:
                txs = []

                if block['height'] < config['startBlock']:
                    for tx in block['transactions']:
                        if tx['type'] == 8 or tx['type'] == 9:
                            txs.append(tx)
                else:
                    txs = block['transactions']

                block['transactions'] = txs

        blocks += cleanBlocks(blocksJSON)

        if (startblock + steps < endBlock):
            startblock += steps
        else:
            startblock = endBlock
        
    return blocks

def prepareDataStructure(blocks):
    global myLeases
    global myCanceledLeases
    global myForgedBlocks
    prevBlock = None

    for block in blocks:
        fee = 0

        if block['generator'] == config['address']:
            myForgedBlocks.append(block)

        for tx in block['transactions']:
            if (tx['type'] == 8) and (tx['recipient'] == config['address'] or tx['recipient'] == 'address:' + config['address'] or tx['recipient'] == 'alias:L:' + config['alias']):
                tx['block'] = block['height']
                myLeases[tx['id']] = tx
            elif (tx['type'] == 9) and (tx['leaseId'] in myLeases):
                tx['block'] = block['height']
                myCanceledLeases[tx['leaseId']] = tx

        if prevBlock is not None:
            block['previousBlockFees'] = prevBlock['fee']

        prevBlock = block

    return blocks

def getActiveLeasesAtBlock(block):
    global myLeases
    global myCanceledLeases

    activeleases = []
    totalLeased = 0
    activeLeasesPerAddress = {}

    for key in myLeases:
        currentLease = myLeases[key]

        if not(key in myCanceledLeases) or myCanceledLeases[key]['block'] > block['height']:
            activeleases.append(currentLease)

    for lease in activeleases:
        if block['height'] > lease['block'] + 1000:
            if lease['sender'] in activeLeasesPerAddress:
                activeLeasesPerAddress[lease['sender']] += lease['amount']
            else:
                activeLeasesPerAddress[lease['sender']] = lease['amount']

            totalLeased += lease['amount']

    return {'totalLeased': totalLeased, 'activeLeases': activeLeasesPerAddress}

def distribute(activeLeases, amountTotalLeased, block):
    global payments
    global totalfee

    fee = block['fee'] * 0.4 + block['previousBlockFees'] * 0.6
    totalfee += fee

    for address in activeLeases:
        share = activeLeases[address] / amountTotalLeased
        amount = fee * share

        if address in payments:
            payments[address] += amount * (config['percentageOfFeesToDistribute'] / 100)
        else:
            payments[address] = amount * (config['percentageOfFeesToDistribute'] / 100)

def checkTotalDistributableAmount(payments):
    total = 0

    for address in payments:
        amount = payments[address]

        total += amount

    return total

def createPayment():
    global payments
    tx = []

    for address in payments:
        if round(payments[address]) > config['minAmounttoPay']:
            paytx = {'recipient': address, 'amount': round(payments[address])}
            tx.append(paytx)

    with open(config['paymentStorage'], 'w') as outfile:
        hyperjson.dump(tx, outfile)
    
    print('payments written to ' + config['paymentStorage'])


def main():
    global payments
    global myForgedBlocks
    global myLeases
    global myCanceledLeases

    print('getting blocks...')
    blocks = getAllBlocks()
    print('preparing datastructures...')
    blocks = prepareDataStructure(blocks)

    #clear payed tx
    for block in blocks:
        txs = []

        if block['height'] < config['startBlock']:
            for tx in block['transactions']:
                if tx['type'] == 8 or tx['type'] == 9:
                    txs.append(tx)
        else:
            txs = block['transactions']

        block['transactions'] = txs

    #save current blocks
    print('saving blockfile...')
    with open(config['blockStorage'], 'w') as outfile:
        hyperjson.dump(blocks, outfile)

    print('preparing payments...')
    if config['endBlock'] == 0:
        endBlock = requests.get(config['node'] + '/blocks/height').json()['height'] - 1
    else:
        endBlock = config['endBlock']

    for block in myForgedBlocks:
        if block['height'] >= config['startBlock'] and block['height'] <= endBlock:
            blockLeaseData = getActiveLeasesAtBlock(block)
            activeLeasesForBlock = blockLeaseData['activeLeases']
            amountTotalLeased = blockLeaseData['totalLeased']

            distribute(activeLeasesForBlock, amountTotalLeased, block)

    #remove excluded addresses
    for exclude in config['excludeListTN']:
        payments[exclude] = 0
        print('excluding: ' + exclude)

    total = checkTotalDistributableAmount(payments)
    createPayment()

    print('forged blocks: ' + str(len(myForgedBlocks)))
    print('number of payments: ' + str(len(payments)))
    print('total payment: ' + str(total / pow(10, 8)))
    print('number of leases: ' + str(len(myLeases)))
    print('number of cancelled leases: ' + str(len(myCanceledLeases)))

main()
