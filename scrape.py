from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import os
from datetime import datetime, timezone, timedelta
import time
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
import time
import csv
import glob
import json
from pathlib import Path

PROGRAM_URL = 'https://s2025.conference-schedule.org'
MY_LOGIN = 'fhahnlei@cs.washington.edu'
MY_PASSWORD = '25-9262'
AGENDA_ITEMS_FILE = 'agenda_items-2025.csv'

def read_agenda_items(file_name):
    with open(file_name, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        agenda_items = [dict(row) for row in reader]
    return agenda_items

def write_agenda_items(file_name, agenda_items):
    all_keys = sorted(list(set().union(*(it.keys() for it in agenda_items))))
    with open(file_name, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, all_keys)
        dict_writer.writeheader()
        dict_writer.writerows(agenda_items)

def start_driver():
    # Go to Login Page
    driver = webdriver.Firefox()
    login_url = f'{PROGRAM_URL}/wp-login.php'

    driver.get(login_url)
    assert("Log In" in driver.title)

    # Log in
    login_elem = driver.find_element(By.ID, 'user_login')
    login_elem.clear()
    login_elem.send_keys(MY_LOGIN)

    password_elem = driver.find_element(By.ID, 'user_pass')
    password_elem.clear()
    password_elem.send_keys(MY_PASSWORD)

    submit_elem = driver.find_element(By.ID, 'wp-submit')
    submit_elem.click()

    time.sleep(2)

    return driver

def scrape_agenda_items(limit=None):
    driver = start_driver()
    
    # List agenda items
    agenda_items = [{'html' : it.get_property('outerHTML')} for it in driver.find_elements(By.CSS_SELECTOR, '.agenda-item')]
    print(f"Found {len(agenda_items)} agenda items.")
    if limit is not None:
        agenda_items = agenda_items[:limit]
        print(f"Clamped to {len(agenda_items)}.")
        
    for i, it in enumerate(agenda_items):
        it['id'] = i
        soup = BeautifulSoup(it['html'], 'lxml')
        
        title_elems = soup.select('.title-speakers-td > a')
        if len(title_elems) == 0:
            title_elems = soup.select('.presentation-title > a')
            
        if len(title_elems) > 0:
            if 'href' in title_elems[0].attrs:
                full_url = PROGRAM_URL + '/' + title_elems[0].get('href')
                it['presentation_url'] = full_url
        print(f"Item {i} : url = ", it.get('presentation_url'))

    for i, it in enumerate(agenda_items):
        print(f"Scraping {i + 1} / {len(agenda_items)}")
        url = it.get('presentation_url')
        if url is not None:
            driver.get(url)

            try:
                main_video = driver.find_element(By.ID, 'main_video')
                vimeo_url = main_video.get_property('src')
            except NoSuchElementException as e:
                continue

            if 'event' in vimeo_url:
                try:
                    driver.switch_to.frame(main_video)
                    time.sleep(1)
                    fallback_url = driver.find_element(By.CSS_SELECTOR, 'div.player').get_attribute('data-fallback-url')
                    vimeo_url = 'https://player.vimeo.com/video/' + fallback_url.split('/')[4]
                except Exception as e:
                    continue

            it['video_url'] = vimeo_url

    return agenda_items

def make_video_file_path(agenda_item):
    video_name = agenda_item['title']
    
    video_name = video_name.replace('/', '-').replace(' ', '-')
    video_name = ''.join(c for c in video_name if c.isalnum() or c == '-').lower()

    extension = '.mp4'
    max_length = 128
    if len(video_name) + len(extension) > max_length:
        video_name = video_name[:max_length - len(extension)]
    video_name = video_name + extension

    video_path = 'videos/' + video_name

    return video_path

def enrich_agenda_items(agenda_items):
    type = None
    for i, it in enumerate(agenda_items):
        soup = BeautifulSoup(it['html'], 'lxml')
        start_utc = soup.html.body.find('tr', recursive=False).attrs.get('s_utc', '')
        start_utc = datetime.fromisoformat(start_utc[:-1]).replace(tzinfo=timezone.utc)
        end_utc = soup.html.body.find('tr', recursive=False).attrs.get('e_utc', '')
        end_utc = datetime.fromisoformat(end_utc[:-1]).replace(tzinfo=timezone.utc)

        presenter_divs = soup.select('.presenter-details')
        presenter_names = [node.div.a.text for node in presenter_divs]
        
        speaker_divs = soup.select('.presenter-details.presenting')
        speaker_names = [node.div.a.text for node in speaker_divs]

        title_elems = soup.select('.title-speakers-td > a')
        if len(title_elems) == 0:
            title_elems = soup.select('.title-speakers-td')
        if len(title_elems) == 0:
            title_elems = soup.select('.presentation-title')
        title = title_elems[0].text

        type_elems = soup.select('.presentation-type')
        if len(type_elems) > 0:
            type = type_elems[0].text

        mdt = timezone(timedelta(hours=-6))
        start_mdt = start_utc.astimezone(mdt)
        end_mdt = end_utc.astimezone(mdt)

        it['title'] = title
        it['type'] = type
        it['start_utc'] = str(start_utc)
        it['end_utc'] = str(end_utc)
        it['start_mdt'] = str(start_mdt)
        it['end_mdt'] = str(end_mdt)
        it['presenters'] = presenter_names
        it['speakers'] = speaker_names

        assert('Authors' not in title)
        assert('Contributors' not in title)

def download_videos(agenda_items):
    failed_downloads = []
    with YoutubeDL(params={'http_headers': {'Referer':PROGRAM_URL}}) as ydl:
        for i, it in enumerate(agenda_items):
            print(f"Downloading video for item {i + 1}/{len(agenda_items)} : {it['title']}")

            prev_video_file_path = it.get('video_file_path')
            new_video_file_path = make_video_file_path(it)
            Path(new_video_file_path).parent.mkdir(parents=True, exist_ok=True)

            if prev_video_file_path and len(prev_video_file_path) > 0 and os.path.isfile(prev_video_file_path):
                print(f"Video file '{prev_video_file_path}' already exists.")
                if prev_video_file_path != new_video_file_path:
                    os.rename(prev_video_file_path, new_video_file_path)
                    it['video_file_path'] = new_video_file_path
            elif new_video_file_path and len(new_video_file_path) > 0 and os.path.isfile(new_video_file_path):
                print(f"Video file '{new_video_file_path}' already exists.")
            else:
                try:
                    if 'video_url' in it and len(it['video_url']) > 0:
                        info = ydl.extract_info(it['video_url'], download=False)
                        download_file_path = ydl.prepare_filename(info)
                        ydl.process_info(info)
                        os.rename(download_file_path, new_video_file_path)
                        it['video_file_path'] = new_video_file_path
                    else:
                        it['video_file_path'] = ''
                except Exception as e:
                    failed_downloads.append(it)

                    it['video_file_path'] = ''
                    print(f"Video download failed! {it['title']} : {e}")
                    print(e)
    return failed_downloads

if __name__ == '__main__':
    try:
        agenda_items = read_agenda_items(AGENDA_ITEMS_FILE)
    except FileNotFoundError:
        agenda_items = scrape_agenda_items()
        enrich_agenda_items(agenda_items)
        write_agenda_items(AGENDA_ITEMS_FILE, agenda_items)

    failed = download_videos(agenda_items)

    with open('index_template.js', encoding='utf-8') as index_js:
        index_js_code = index_js.read()

    agenda_items_stripped = []
    for it in agenda_items:
        it_stripped = dict(it)
        del it_stripped['html']
        agenda_items_stripped.append(it_stripped)

    with open('index.js', 'w', encoding='utf-8') as index_js:
        index_js.write(f'const data = {json.dumps(agenda_items_stripped)};\n')
        index_js.write(index_js_code)

# print(json.dumps(agenda_items))
