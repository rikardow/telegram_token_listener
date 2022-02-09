import logging
import os
import time
from typing import Tuple

import requests
from web3 import Web3, Account
from web3.middleware import geth_poa_middleware

from tokens import Tokens


class Pancake:
    router = None
    router_address = Web3.toChecksumAddress('0x10ed43c718714eb63d5aa57b78b54704e256024e')
    factory = None
    factory_address = Web3.toChecksumAddress('0xca143ce32fe78f1f7019d7d551a6402fc5350c73')
    token_contract = None
    account: Account
    web3: Web3

    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider(os.environ.get('BSC_URL')))
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.account = self.web3.eth.account.from_key(os.environ.get('PRIVATE_KEY'))
        self.init_router()
        self.init_factory()
        self.init_base_token()

    def init_router(self):
        router_abi_file = open('contracts/pancake_router.abi', 'r')
        router_abi = router_abi_file.read()

        router_bytecode_file = open('contracts/pancake_bytecode.txt', 'r')
        router_bytecode = router_bytecode_file.read()

        self.router = self.web3.eth.contract(abi=router_abi, bytecode=router_bytecode, address=self.router_address)

    def init_factory(self):
        factory_abi_file = open('contracts/pancake_factory.abi', 'r')
        factory_abi = factory_abi_file.read()

        factory_bytecode_file = open('contracts/pancake_factory_bytecode.txt', 'r')
        factory_bytecode = factory_bytecode_file.read()

        self.factory = self.web3.eth.contract(abi=factory_abi, bytecode=factory_bytecode, address=self.factory_address)

    def init_base_token(self):
        token_abi_file = open('contracts/bep20_token.abi', 'r')
        token_abi = token_abi_file.read()

        token_bytecode_file = open('contracts/bep20_token_bytecode.txt', 'r')
        token_bytecode = token_bytecode_file.read()

        self.token_contract = self.web3.eth.contract(abi=token_abi, bytecode=token_bytecode)

    # https://stackoverflow.com/questions/57580702/how-to-call-a-smart-contract-function-using-python-and-web3-py
    def buy_tokens(self, token: str, bnb_pair: bool):
        token = Web3.toChecksumAddress(token)
        amount = int(os.environ.get('BUY_AMOUNT'))

        path = [Tokens.busd]
        if bnb_pair:
            logging.info('The token is BNB pair, adding to the router path')
            path.append(Tokens.bnb)
        path.append(token)

        transaction = self.router.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
            amountIn=Web3.toWei(amount, 'ether'),
            amountOutMin=0,
            path=path,
            to=self.account.address,
            deadline=int(time.time()) + 4 * 60 * 60,  # Add 4 hours
        ).buildTransaction({
            'gasPrice': Web3.toWei(int(os.environ.get('GAS_PRICE')), 'gwei'),
            'from': self.account.address,
            'nonce': self.web3.eth.get_transaction_count(self.account.address)
        })

        transaction['gas'] = int(transaction.get('gas') * float(os.environ.get('GAS_MULTIPLIER')))

        signed_transaction = self.account.sign_transaction(transaction)
        tx_hash = self.web3.eth.send_raw_transaction(signed_transaction.rawTransaction)
        logging.info(f'Transaction: https://bscscan.com/tx/{tx_hash.hex()}')

    def check_liquidity(self, token: str) -> Tuple[bool, bool]:
        """ returns Tuple[has_liquidity, is_bnb_pair] """
        token = Web3.toChecksumAddress(token)

        bnb_lp = self.factory.functions.getPair(token, Tokens.bnb).call()
        busd_lp = self.factory.functions.getPair(token, Tokens.busd).call()
        # logging.info(self.factory.functions.getPair(token, Token.usdt).call())

        logging.info(f'BNB Liquidity Pool: {bnb_lp}')
        logging.info(f'BUSD Liquidity Pool: {busd_lp}')

        bnb_amount = self.get_balance(token=Tokens.bnb, wallet=bnb_lp) if Web3.toInt(hexstr=bnb_lp) > 0 else 0
        busd_amount = self.get_balance(token=Tokens.busd, wallet=busd_lp) if Web3.toInt(hexstr=busd_lp) > 0 else 0

        if bnb_amount > 0:
            bnb_amount = self.bnb_to_usd(bnb_amount)

        logging.info(f'BNB Liquidity Pool Reserves: {int(bnb_amount)} USD')
        logging.info(f'BUSD Liquidity Pool Reserves: {int(busd_amount)} BUSD')

        if bnb_amount > 0 or busd_amount > 0:
            bnb_pair = bnb_amount > busd_amount
            return True, bnb_pair

        return False, False

    def get_balance(self, token: str, wallet: str) -> float:
        self.token_contract = self.web3.eth.contract(
            abi=self.token_contract.abi,
            bytecode=self.token_contract.bytecode,
            address=Web3.toChecksumAddress(token)
        )

        wallet = Web3.toChecksumAddress(wallet)

        wei_amount = self.token_contract.functions.balanceOf(wallet).call()
        eth_amount = Web3.fromWei(wei_amount, 'ether')
        return eth_amount

    @staticmethod
    def bnb_to_usd(bnb_amount: float) -> float:
        result = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=BNBUSDT')
        price = int(float(result.json().get('price')))

        logging.info(f'BNB price {price} USD')
        return price * bnb_amount
