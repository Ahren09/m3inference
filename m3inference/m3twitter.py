#!/usr/bin/env python3
# @Scott Hale

import configparser
import html
import json
import logging
import os
import os.path as osp
from os.path import expanduser
from rauth import OAuth1Service

from .consts import UNKNOWN_LANG, TW_DEFAULT_PROFILE_IMG
from .m3inference import M3Inference
from .preprocess import download_resize_img
from .utils import get_lang

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
    datefmt='%m/%d/%Y %H:%M:%S',
    level=logging.INFO)

logger = logging.getLogger(__name__)


def get_extension(img_path):
    if '.' not in img_path.split('/')[-1]:
        return 'png'
    dotpos = img_path.rfind(".")
    extension = img_path[dotpos + 1:]
    if extension.lower() == "gif":
        return "png"
    return extension


class M3Twitter(M3Inference):

    def __init__(self, data_dir, cache_dir="cache", model_dir="models/",
                 pretrained=True,
                 use_full_model=True, use_cuda=True, parallel=False, seed=0,
                 skip_logging=False, id2name=None):
        super(M3Twitter, self).__init__(model_dir=model_dir,
                                        pretrained=pretrained,
                                        use_full_model=use_full_model,
                                        use_cuda=use_cuda, parallel=parallel,
                                        seed=seed, skip_logging=skip_logging)
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.id2name = id2name
        self.twitter_session = None
        if not os.path.isdir(self.cache_dir):
            logger.info(f'Dir {self.cache_dir} does not exist. Creating now.')
            os.makedirs(self.cache_dir)
            logger.info(f'Dir {self.cache_dir} created.')

    def transform_jsonl(self, input_file, output_file, img_path_key=None,
                        lang_key=None, resize_img=True,
                        keep_full_size_img=False):
        with open(input_file, "r") as fhIn:
            with open(output_file, "w") as fhOut:
                for line in fhIn:
                    m3vals = self.transform_jsonl_object(line,
                                                         img_path_key=img_path_key,
                                                         lang_key=lang_key,
                                                         resize_img=resize_img,
                                                         keep_full_size_img=keep_full_size_img)
                    fhOut.write("{}\n".format(json.dumps(m3vals)))

    def transform_jsonl_object(self, input, img_path_key=None, lang_key=None,
                               resize_img=True,
                               keep_full_size_img=False):
        """
        input is either a Twitter tweet object (https://developer.twitter.com/en/docs/tweets/data-dictionary/overview/tweet-object)
            or a Twitter user object (https://developer.twitter.com/en/docs/tweets/data-dictionary/overview/user-object)
        """
        if isinstance(input, str):
            input = json.loads(input)

        if "user" in input:
            user = input["user"]
        else:
            user = input

        if img_path_key != None and img_path_key in user:
            img_path = user[img_path_key]
            if resize_img:
                img_file_resize = "{}/{}_224x224.{}".format(self.cache_dir,
                                                            user["id_str"],
                                                            get_extension(
                                                                img_path))
                download_resize_img(img_path, img_file_resize)
            else:
                img_file_resize = img_path
        elif img_path_key != None and img_path_key in input:
            img_path = input[img_path_key]
            if resize_img:
                img_file_resize = "{}/{}_224x224.{}".format(self.cache_dir,
                                                            user["id_str"],
                                                            get_extension(
                                                                img_path))
                download_resize_img(img_path, img_file_resize)
            else:
                img_file_resize = img_path
        elif user["default_profile_image"]:
            # Default profile image
            img_file_resize = TW_DEFAULT_PROFILE_IMG
        else:
            img_path = user["profile_image_url_https"]
            img_path = img_path.replace("_normal", "_400x400")
            dotpos = img_path.rfind(".")
            img_file_full = "{}/{}.{}".format(self.cache_dir, user["id_str"],
                                              img_path[dotpos + 1:])
            img_file_resize = "{}/{}_224x224.{}".format(self.cache_dir,
                                                        user["id_str"],
                                                        get_extension(img_path))
            if not os.path.isfile(img_file_resize):
                if keep_full_size_img:
                    download_resize_img(img_path, img_file_resize,
                                        img_file_full)
                else:
                    download_resize_img(img_path, img_file_resize)
        # check if an error occurred and the image was not downloaded
        if not os.path.exists(img_file_resize):
            img_file_resize = TW_DEFAULT_PROFILE_IMG

        bio = user["description"]
        if bio == None:
            bio = ""

        if lang_key != None and lang_key in user:
            lang = user[lang_key]
        elif lang_key != None and lang_key in input:
            lang = input[lang_key]
        elif bio == "":
            lang = UNKNOWN_LANG
        else:
            lang = get_lang(bio)

        output = {
            "description": bio,
            "id": user["id_str"],
            "img_path": img_file_resize,
            "lang": lang,
            "name": user["name"],
            "screen_name": user["screen_name"]
        }
        return output

    def infer_screen_name(self, screen_name, skip_cache=False):
        """
        Collect data for a Twitter screen name from the Twitter website and predict attributes with m3
        :param scren_name: A Twitter screen_name. Do not include the "@"
        :param skip_cache: If output for this screen name already exists in self.cache_dir, the results will be reused (i.e., the function will not contact the Twitter website and will not run m3).
        :return: a dictionary object with two keys. "input" contains the data from the Twitter website. "output" contains the m3 output in the `output_format` format described for m3.
        """
        screen_name = screen_name.lower()
        if screen_name[0] == "@":
            screen_name = screen_name[1:]
        if not skip_cache:
            # If a json file exists, we'll use that. Otherwise go get the data.
            try:
                with open("{}/{}.json".format(self.cache_dir, screen_name),
                          "r") as fh:
                    logger.info(
                        "Results from cache for {}.".format(screen_name))
                    return json.load(fh)
            except:
                logger.info(
                    "Results not in cache. Fetching data from Twitter for {}.".format(
                        screen_name))
        else:
            logger.info(
                "skip_cache is True. Fetching data from Twitter for {}.".format(
                    screen_name))

        output = self._twitter_api(screen_name=screen_name)
        with open("{}/{}.json".format(self.cache_dir, screen_name), "w") as fh:
            json.dump(output, fh)
        return output

    def twitter_init_from_file(self, auth_file):
        with open(auth_file, "r") as fh:
            config_string = '[DEFAULT]\n' + fh.read()
            config = configparser.ConfigParser()
            config.read_string(config_string)
            twcfg = dict(config.items("DEFAULT"))
        return self.twitter_init(**twcfg)

    def twitter_init(self, api_key, api_secret, access_token, access_secret):
        twitter = OAuth1Service(
            consumer_key=api_key,
            consumer_secret=api_secret,
            request_token_url='https://api.twitter.com/oauth/request_token',
            access_token_url='https://api.twitter.com/oauth/access_token',
            authorize_url='https://api.twitter.com/oauth/authorize',
            base_url='https://api.twitter.com/1.1/')
        self.twitter_session = twitter.get_session(
            token=[access_token, access_secret])
        return True

    def _twitter_api(self, id=None, screen_name=None):
        if self.twitter_session == None:
            logger.fatal(
                "You must call twitter_init(...) before using this method. Please see https://github.com/euagendas/m3inference/blob/master/README.md for details.")
            return None

        if screen_name != None:
            logger.info(
                "GET /users/show.json?screen_name={}".format(screen_name))
            try:
                r = self.twitter_session.get("users/show.json", params={
                    "screen_name": screen_name
                })
            except:
                logger.warning("Invalid response from Twitter")
                return None
        elif id != None:
            logger.info("GET /users/show.json?id={}".format(id))
            try:
                r = self.twitter_session.get("users/show.json", params={
                    "id": id
                })



            except:
                logger.warning("Invalid response from Twitter")
                return None
            if r.status_code != 200:
                raise Exception(f"Response {r.status_code} from Twitter")

        else:
            logger.fatal("No id or screen_name")
            return None

        return self.process_twitter(r.json())

    def infer_id(self, id, skip_cache=False):
        """
        Collect data for a numeric Twitter user id from the Twitter website and predict attributes with m3
        :param id: A Twitter numeric user id
        :param skip_cache: If output for this screen name already exists in self.cache_dir, the results will be reused (i.e., the function will not contact the Twitter website and will not run m3).
        :return: a dictionary object with two keys. "input" contains the data from the Twitter website. "output" contains the m3 output in the `output_format` format described for m3.
        """
        if not skip_cache:
            # If a json file exists, we'll use that. Otherwise go get the data.
            try:
                with open("{}/{}.json".format(self.cache_dir, id), "r") as fh:
                    logger.info("Results from cache for id {}.".format(id))
                    return json.load(fh)
            except:
                logger.info(
                    "Results not in cache. Fetching data from Twitter for id {}.".format(
                        id))
        else:
            logger.info(
                "skip_cache is True. Fetching data from Twitter for id {}.".format(
                    id))

        output = self._twitter_api(id=id)
        with open("{}/{}.json".format(self.cache_dir, id), "w") as fh:
            json.dump(output, fh, indent=2, sort_keys=True)
        return output

    def _get_twitter_attrib(self, key, data):
        if key in data:
            return data[key]
        else:
            logger.warning("Could not retrieve {}".format(key))
            return ""

    def process_twitter(self, data):

        screen_name = self._get_twitter_attrib("screen_name", data)
        id = self._get_twitter_attrib("id_str", data)
        bio = self._get_twitter_attrib("description", data)
        name = self._get_twitter_attrib("name", data)
        img_path = self._get_twitter_attrib("profile_image_url", data)
        if id == "":
            id = "dummy"  # Can be anything since batch is of size 1

        if bio == "":
            lang = UNKNOWN_LANG
        else:
            lang = get_lang(bio)

        if img_path == "" or "default_profile" in img_path:
            logger.warning(
                "Unable to extract image from Twitter. Using default image.")
            img_file_resize = TW_DEFAULT_PROFILE_IMG
        else:
            img_path = img_path.replace("_200x200", "_400x400").replace(
                "_normal", "_400x400")
            img_file_full = f"{self.cache_dir}/{id}" + (
                f".{img_path[img_path.rfind('.') + 1:]}" if '.' in
                                                            img_path.split('/')[
                                                                -1] else '')
            img_file_resize = "{}/{}_224x224.{}".format(self.cache_dir, id,
                                                        get_extension(img_path))
            #             img_file_full = "{}/{}.{}".format(self.cache_dir, screen_name, img[dotpos + 1:])
            #             img_file_resize = "{}/{}_224x224.{}".format(self.cache_dir, screen_name, get_extension(img))
            download_resize_img(img_path, img_file_resize, img_file_full)

        data = [{
            "description": bio,
            "id": id,
            "img_path": img_file_resize,
            "lang": lang,
            "name": name,
            "screen_name": screen_name,
        }]

        pred = self.infer(data, batch_size=1, num_workers=0)

        output = {
            "input": data[0],
            "output": pred[id]
        }
        return output

    def process_twitter_batch(self, data):
        import torch

        if osp.exists("users_li.pt"):
            users_li = torch.load("users_li.pt")

        else:
            users_li = []
            for user in tqdm(data, desc="Processing Twitter users"):

                screen_name = self._get_twitter_attrib("screen_name", user)
                id = user.get("id", "")
                bio = user.get("description", "")
                name = user.get("name", "")
                img_path = user.get("profile_image_url", "")
                if id == "":
                    id = "dummy"  # Can be anything since batch is of size 1

                if bio == "":
                    lang = UNKNOWN_LANG
                else:
                    lang = get_lang(bio)

                if img_path == "" or "default_profile" in img_path:
                    logger.warning(
                        "Unable to extract image from Twitter. Using default image.")
                    img_file_resize = TW_DEFAULT_PROFILE_IMG
                else:

                    img_path = img_path.replace("_200x200", "_400x400").replace(
                        "_normal", "_400x400")

                    img_full_dir = osp.join(self.data_dir, "profile_img_full")
                    img_resize_dir = osp.join(self.data_dir, "profile_img_resize")

                    os.makedirs(img_full_dir, exist_ok=True)
                    os.makedirs(img_resize_dir, exist_ok=True)

                    img_file_full = f"{img_full_dir}/{id}" + (
                        f".{img_path[img_path.rfind('.') + 1:]}" if '.' in
                                                                    img_path.split(
                                                                        '/')[
                                                                        -1] else '')
                    img_file_resize = "{}/{}_224x224.{}".format(img_resize_dir, id,
                                                                get_extension(
                                                                    img_path))

                    if osp.exists(img_file_resize):
                        pass
                        # with open(img_file_resize, 'rb') as f:
                        #     img_file_resize = f.read()

                    download_resize_img(img_path, img_file_resize, img_file_full)

                users_li += [{
                    "description": bio,
                    "id": id,
                    "img_path": img_file_resize,
                    "lang": lang,
                    "name": name,
                    "screen_name": screen_name,
                }]

        preds = self.infer(users_li, batch_size=64, num_workers=0)

        outputs = []
        os.makedirs(osp.join(self.data_dir, "inferred_user_attributes"), exist_ok=True)
        num_errors = 0

        for idx_user, (user_id, pred) in enumerate(preds.items()):
            assert data[idx_user]["id"] == user_id
            try:
                name = self.id2name[user_id]
                json.dump(pred, open(osp.join(self.data_dir, "inferred_user_attributes", f"{name}.json"), "w", encoding='utf-8'), indent=2, sort_keys=True)

            except:
                num_errors += 1
                print(f"{num_errors}-th error: user {user_id}")

            # output = {
            #     "input": data[idx_user],
            #     "output": pred,
            # }
            # outputs += [output]

        # return outputs
