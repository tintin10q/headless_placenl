import os
from copy import copy
from datetime import datetime
from pprint import pprint
from typing import Literal
from urllib.parse import urlparse

import ojson
import ojson as json
import requests
import websockets

from colors import GREEN, printc, RESET, RED, AQUA, YELLOW, LIGHTAQUA, PURPLE
from config import Config, load_config_without_auth, ratelimitreportpath

from dataclasses import dataclass

import time

from now import now, now_usr

from collections import defaultdict
import pathlib

import atexit

rate_limited_usernames = defaultdict(int)
rate_limit_limit = 2


def show_ratelimited_acocunts():
    if rate_limited_usernames:
        print()
        print(f"{PURPLE}== Rate Limit Report =={RESET}")
        print(f"{YELLOW}Accounts are stopped after being rate limited {rate_limit_limit} times")
        print(f"{YELLOW}These accounts got rate limited:{RESET}")
        for index, (username, ratelimit_count) in enumerate(rate_limited_usernames.items()):
            print(f"{GREEN}- {AQUA if index % 2 == 0 else LIGHTAQUA}{username}{GREEN}, rate limited {AQUA}{ratelimit_count}{GREEN} times{RESET}")
    else:
        print(f"{GREEN}No accounts were rate limited!{RESET}")
    write_ratelimitreport_to_file()


def write_ratelimitreport_to_file(filename=ratelimitreportpath):
    filepath = pathlib.Path(filename)
    filepath = filepath.parent.joinpath((date_str() + filepath.name))

    if rate_limited_usernames:
        filename = date_str() + filename
        print(f"{now()} {GREEN}Writing rate limit report to {filename}{RESET}")
        with open(filepath, 'w+') as ratelimitreportfile:
            print(f"== Rate Limit Report ==", file=ratelimitreportfile)
            print(f"Accounts were stopped after being rate limited {rate_limit_limit} times", file=ratelimitreportfile)
            print("These accounts might have gotten rate limited:", file=ratelimitreportfile)
            for index, (username, ratelimit_count) in enumerate(rate_limited_usernames.items()):
                print(f"- {username}, rate limited {ratelimit_count} times", file=ratelimitreportfile)
    else:
        with open(filepath, 'w+') as ratelimitreportfile:
            print("No accounts were rate limited!", file=ratelimitreportfile)


atexit.register(show_ratelimited_acocunts)


@dataclass
class Coordinates:
    x: int
    y: int
    canvasIndex: int


def ui_to_req_coords(displayX, displayY) -> Coordinates:
    canvasX = (displayX + 500) % 1000
    canvasY = (displayY + 1000) % 1000
    if displayY < 0:
        if displayX < -500:
            canvas = 0
        elif displayX > 499:
            canvas = 2
        else:
            canvas = 1
    else:
        if displayX < -500:
            canvas = 3
        elif displayX > 499:
            canvas = 5
        else:
            canvas = 4
    return Coordinates(canvasX, canvasY, canvas)


VALID_COLORS = ['#6D001A', '#BE0039', '#FF4500', '#FFA800', '#FFD635', '#FFF8B8', '#00A368', '#00CC78', '#7EED56', '#00756F', '#009EAA', '#00CCC0', '#2450A4', '#3690EA', '#51E9F4', '#493AC1', '#6A5CFF', '#94B3FF', '#811E9F', '#B44AC0',
                '#E4ABFF', '#DE107F', '#FF3881', '#FF99AA', '#6D482F', '#9C6926', '#FFB470', '#000000', '#515252', '#898D90', '#D4D7D9', '#FFFFFF'];


def place_pixel(config: Config, coords: Coordinates, color=3):
    # print("got to the place pixel reqeust", coords)

    data = {
        'operationName': 'setPixel',
        'variables': {
            'input': {
                'actionName': 'r/replace:set_pixel',
                'PixelMessageData': {
                    'coordinate': {"x": coords.x, 'y': coords.y},
                    'colorIndex': color,
                    'canvasIndex': coords.canvasIndex
                }
            }
        },
        'query': 'mutation setPixel($input: ActInput!) {\n  act(input: $input) {\n    data {\n      ... on BasicMessage {\n        id\n        data {\n          ... on GetUserCooldownResponseMessageData {\n            nextAvailablePixelTimestamp\n            __typename\n          }\n          ... on SetPixelResponseMessageData {\n            timestamp\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n'
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/114.0",
        'content-type': 'application/json',
        "authorization": config.auth_token,
        'apollographql-client-name': 'garlic-bread',
        'apollographql-client-version': '0.0.1',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }

    print(config.reddit_uri_https)
    set_pixel = requests.post(config.reddit_uri_https, json=data, headers=headers)
    print(f"{now()} {GREEN}setPixel response: {AQUA if set_pixel.status_code < 300 else RED}{set_pixel.status_code}{GREEN} (should be 200)")
    print(f"set pixel response:{AQUA}")
    pprint(set_pixel.text)
    print(RESET)
    if "error" in set_pixel.text:
        print(f"{now_usr(username=config.reddit_username)} {RED}Got error in setPixel response!{RESET}")
        if 'Ratelimited' in set_pixel.text:
            print(f"{now_usr(username=config.reddit_username)} {RED}The error is a rate limit error, {AQUA}{config.reddit_username}{RED} might not work anymore!{RESET}")
            rate_limited_usernames[config.reddit_username] += 1
            if rate_limited_usernames[config.reddit_username] > rate_limit_limit:
                raise RateLimitLimitReached(f"Rate limited more than {rate_limit_limit} times", rate_limit_times=rate_limited_usernames[config.reddit_username])
            else:
                raise RateLimitReached(f"{config.reddit_username} got rate limited", rate_limit_times=rate_limited_usernames[config.reddit_username])


class RateLimitLimitReached(Exception):
    """ Raise this if you want the client to stop """

    def __init__(self, *args, rate_limit_times: int):
        super().__init__(*args)
        self.rate_limit_times = rate_limit_times


class RateLimitReached(Exception):
    """ Raise this if you want the client to let the client know a rate limit happened and when the next pixel is available """

    def __init__(self, *args, rate_limit_times: int):
        super().__init__(*args)
        self.rate_limit_times = rate_limit_times


def date_str() -> str:
    now = datetime.now()
    formatted_date = now.strftime("%Y-%m-%d_%H:%M:%S")
    return formatted_date


# return data.data.act.data.find((e) => e.data.__typename === 'GetUserCooldownResponseMessageData').data.nextAvailablePixelTimestamp;


def test_authorization(authorization: str) -> bool:
    """ Returns true if the authorization is actually valid
        We could either do this by actually verifying the jwt or by just making a request
        I can't find reddits public key, so I guess we have to just try use it
    """
    return get_nextAvailablePixelTimestamp(authorization) is not None


def get_proxied_url(garlic_url):
    url = urlparse(garlic_url)
    return f"https://garlic-proxy.placenl.nl/{url.path.replace('/media/', '')}?bust={int(time.time() * 1000)}"


async def get_canvas_url(canvas_id: Literal[0, 1, 2, 3, 4, 5], username: str = None) -> str:
    # todo we can also fetch a new anon token for from reddit because anons can also view the canvas

    # todo we could also have an image class which keeps the socket connection open and updates the differences

    config = load_config_without_auth()
    printc(f"{now_usr(username=username)} {GREEN}Fetching canvas with id: {AQUA}{canvas_id}{GREEN}")

    anon_authorization = get_anon_authorization()

    async with websockets.connect(config.reddit_uri_wss, origin="https://garlic-bread.reddit.com") as websocket:
        connection_init_message = {
            "type": 'connection_init',
            "payload": {
                "Authorization": anon_authorization
            }
        }

        await websocket.send(json.dumps(connection_init_message))

        await websocket.recv()  # This should be {"type":"connection_ack"}

        url_message = {
            "id": "2",
            "type": "start",
            "payload": {
                "variables": {
                    "input": {
                        "channel": {
                            "teamOwner": "GARLICBREAD",
                            "category": "CANVAS",
                            "tag": str(canvas_id)
                        }
                    }
                },
                "extension": {},
                "operationName": "replace",
                "query": "subscription replace($input: SubscribeInput!) { subscribe(input: $input) { id ... on BasicMessage { data { __typename ... on FullFrameMessageData { __typename name timestamp } } __typename } __typename }}"
            }
        }

        await websocket.send(json.dumps(url_message))
        await websocket.recv()  # This is also ack
        result = json.loads(await websocket.recv())  # this is what we want with the link
    match result:
        case {"payload": {"data": {"subscribe": {"data": {"__typename": "FullFrameMessageData", "name": str(canvas_url)}}}}}:
            return canvas_url
        case _:
            raise ValueError(f"Could not fetch canvas with id: {canvas_id}")




def get_place_cooldown(authorization: str, *, username: str = None) -> int:
    """
    If this is 0 there is no cooldown
    :param authorization:
    :return:
    """
    next_time = get_nextAvailablePixelTimestamp(authorization, username=username)
    if next_time is None:
        return 1  # 1 second just in case
    diff = next_time - time.time()
    return int(max((diff, 1)))


def get_nextAvailablePixelTimestamp(authorization: str, *, username: str = None) -> int | None:
    if not authorization:
        return None

    headers = {
        'content-type': 'application/json',
        'authorization': authorization,
        'apollographql-client-name': 'garlic-bread',
        'apollographql-client-version': '0.0.1',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site'
    }

    payload = {

        'query': """
mutation GetPersonalizedTimer{
  act(
    input: {actionName: "r/replace:get_user_cooldown"}
  ) {
    data {
      ... on BasicMessage {
        id
        data {
          ... on GetUserCooldownResponseMessageData {
            nextAvailablePixelTimestamp
          }
        }
      }
    }
  }
}
""",
        'operationName': 'GetPersonalizedTimer',
        'id': None
    }

    response = requests.post('https://gql-realtime-2.reddit.com/query', json=payload, headers=headers)
    # print(response.status_code, response.text)

    data = response.json()
    print(f"{now_usr(username=username)} {GREEN}Cooldown data response: {AQUA}{data}{RESET}")

    if not data.get('data'):
        return None

    ts = data['data']['act']['data'][0]['data']['nextAvailablePixelTimestamp']

    return 0 if not ts else ts / 1000


def get_new_anon_session() -> dict:
    printc(f"{now()} {GREEN}Fetching new anon access token from {RED}reddit{GREEN}, this may take a bit")
    response = requests.get('https://reddit.com/r/place',
                            headers={
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/116.0'
                            })
    body = response.text

    # todo: yuck
    configRaw = body.split('<script id="data">window.___r = ')[1].split(';</script>')[0]
    parsed_config = json.loads(configRaw)

    auth_session = {"accessToken": "Bearer " + copy(parsed_config['user']['session']['accessToken']),
                    "expires_at": parsed_config['user']['session']['expiresIn'] + int(time.time()) - 100}  # copy the user_session, so we can delete the big object

    del parsed_config  # delete the big session dict

    return auth_session


@dataclass
class RedditSession:
    accessToken: str
    expires_at: int

    @staticmethod
    def from_dict(payload) -> "RedditSession":
        match payload:
            case {"accessToken": str(accessToken), "expires_at": int(expires_at)} | {"accessToken": str(accessToken), "expires_at": float(expires_at)}:
                return RedditSession(accessToken, expires_at)
            case _:
                raise ValueError("Could not parse reddit session from dict!")

    def save_to_file(self):
        printc(now(), f"{GREEN}Writing anon reddit session to {AQUA}reddit_session.json!")
        with open('reddit_session.json', 'w+') as reddit_session:
            ojson.dump({"accessToken": self.accessToken, "expires_at": self.expires_at}, reddit_session, indent=2)

    @staticmethod
    def load_from_file() -> "RedditSession":
        printc(now(), f"{GREEN}Reading anon reddit session from {AQUA}reddit_session.json!")
        with open('reddit_session.json', 'r') as reddit_session_file:
            reddit_session = ojson.load(reddit_session_file)
            return RedditSession.from_dict(reddit_session)


__reddit_session: RedditSession | None = None


def get_anon_session() -> RedditSession:
    global __reddit_session

    if not __reddit_session and os.path.exists("reddit_session.json"):
        # first read try the session from the file
        try:
            __reddit_session = RedditSession.load_from_file()
        except ValueError:  # if we can't read from the file get a new session
            printc(now(), RED + "Could not parse anon reddit session from file, fetching again")

            __reddit_session = RedditSession.from_dict(get_new_anon_session())
            __reddit_session.save_to_file()

    elif not __reddit_session:
        __reddit_session = RedditSession.from_dict(get_new_anon_session())
        __reddit_session.save_to_file()

    # Check if the session is still valid, if we already fetched again it should be still valid
    if time.time() > __reddit_session.expires_at:
        printc(now(), RED + "Reddit session is expired fetching a new one!")
        __reddit_session = RedditSession.from_dict(get_new_anon_session())
        __reddit_session.save_to_file()

    return __reddit_session


def get_anon_authorization() -> str:
    """
    :return:  A Bearer ... jwt
    Also retries if it doesn't work
    """
    success = False
    while not success:
        try:
            return get_anon_session().accessToken
        except IndexError:
            print(f"{now()} Could not access token from reddit (IndexError), trying again...")
            time.sleep(1)
