import asyncio
import datetime
from sys import stderr
from web3.auto import w3
import os
from loguru import logger

from galxy import Gasless, Galxy, Gassed

from config import *


async def get_info(id_):
    info = await Galxy.get_info_by_id(id_)
    # print(info)
    data = info["data"]["campaign"]

    # type Gasless or Gas
    status, address_nft, gas_type, number_id, name, chain = (
        data["status"],
        data["gamification"]["nfts"][0]["nft"]["nftCore"]["contractAddress"],
        data["gasType"],
        data["numberID"],
        data["name"],
        data["chain"],
    )

    return status, address_nft, gas_type, number_id, name, chain


def check_claim_data(claim_nft_data, info_nft, address):
    if not claim_nft_data["data"].get("prepareParticipate").get("allow"):
        if (
            claim_nft_data["data"].get("prepareParticipate").get("disallowReason")
            == "Exceed limit, available claim count is 0"
        ):
            logger.info(
                f"CLAIM | INFO | {info_nft[-2]} | {address} | Exceed limit, available claim count is 0"
            )
            return True
        disallow_reason = claim_nft_data['data']['prepareParticipate']['disallowReason']
        logger.info(
            f"CLAIM | FAILED | {info_nft[-2]} | {address} | {disallow_reason}"
        )
        return True
    return False


async def gasless(key, id_, info_nft):
    ADDRESS = w3.eth.account.from_key(key).address

    claim_nft_data = await Galxy.claim(ADDRESS, id_, W, info_nft[-1])

    if check_claim_data(claim_nft_data, info_nft, ADDRESS):
        return

    logger.info(f"CLAIM | PENDING | {info_nft[-2]} | {ADDRESS}")

    TRY = 0
    while True:
        TX = await Gasless.check_tx_galxe(claim_nft_data)
        if TX["data"]["participations"][0]["tx"]:
            logger.success(
                f"CLAIM | SUCCESS | {info_nft[-2]} | {ADDRESS} | {TX['data']['participations'][0]['tx']}"
            )
            return
        else:
            logger.info(f"CLAIM | AWAIT | {info_nft[-2]} | {ADDRESS}")

        TRY += 1
        if TRY >= 6:
            logger.success(f"CLAIM | FAILED | {info_nft[-2]} | {ADDRESS}")
            return
        await asyncio.sleep(10)


async def gassed(key, id_, info_nft):
    ADDRESS = w3.eth.account.from_key(key).address

    claim_nft_data = await Galxy.claim(ADDRESS, id_, W, info_nft[-1])

    if check_claim_data(claim_nft_data, info_nft, ADDRESS):
        return

    gas = Gassed(RPC_BY_CHAIN[info_nft[-1]])

    id_nft = int(info_nft[-3])
    signature = claim_nft_data["data"]["prepareParticipate"]["signature"]
    nft_address = claim_nft_data["data"]["prepareParticipate"]["mintFuncInfo"][
        "nftCoreAddress"
    ]
    powahs = int(
        claim_nft_data["data"]["prepareParticipate"]["mintFuncInfo"]["powahs"][0]
    )
    id_claim = int(
        claim_nft_data["data"]["prepareParticipate"]["mintFuncInfo"]["verifyIDs"][0]
    )

    logger.info(f"CLAIM | PENDING | {info_nft[-2]} | {ADDRESS}")

    tx = await gas.mint(key, id_nft, nft_address, powahs, id_claim, signature)
    if await gas.verif_tx(tx):

        logger.success(f"CLAIM | SUCCESS | {info_nft[-2]} | {ADDRESS} | {tx.hex()}")
    else:
        logger.error(f"CLAIM | FAILED | {info_nft[-2]} | {ADDRESS} | {tx.hex()}")


async def claim_nft_queue(queue: asyncio.Queue):
    while not queue.empty():
        data_account = await queue.get()

        for camp_id in task_list:

            if len(camp_id) > 10:
                camp_id = camp_id.split("/")[-1]

            information_by_id = await get_info(camp_id)
            if information_by_id[0] == "Active":

                if information_by_id[2] == "Gasless":
                    await gasless(data_account, camp_id, information_by_id)

                elif information_by_id[2] == "Gas":
                    await gassed(data_account, camp_id, information_by_id)


async def work():
    queue_id = asyncio.Queue()

    for key in key_list:
        queue_id.put_nowait(key)

    claim_work = [claim_nft_queue(queue_id) for _ in range(STREAMS)]

    await asyncio.gather(*claim_work)


# ***********************************************************************************************************

logger.remove()
logger.add(
    stderr,
    format="<white>{time:HH:mm:ss}</white> | "
    "<level>{level: <2}</level> | "
    "<white>{function}</white> | "
    "<white>{line}</white> - "
    "<white>{message}</white>",
)

date = datetime.datetime.now().utcnow().strftime("%H-%M-%S")
logger.add(f"./log/file_{date}.log")


key_path = os.path.abspath("data_file/key.txt")
with open(key_path, "r") as f:
    key_list = [i for i in [i.strip() for i in f] if i != ""]

task_path = os.path.abspath("data_file/task.txt")
with open(task_path, "r") as f:
    task_list = [i for i in [i.strip() for i in f] if i != ""]

w_path = os.path.abspath("data_file/W.txt")
with open(w_path, "r") as f:
    W = f.readline().strip()

# ***********************************************************************************************************


async def main():
    assert len(key_list) > 0, "Add private key key.txt"
    assert (
        len(task_list) > 0
    ), "Add campaign id task.txt | format galxe.com/perp/campaign/XXXXXX OR GCUEJK"

    if not await Galxy.validation_config_w(W):
        logger.info("Invalid W.txt captcha")
        return
    else:
        await work()
