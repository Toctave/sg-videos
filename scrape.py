from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import os
from datetime import datetime, timezone, timedelta

import jinja2

from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
import time
import csv

MY_LOGIN = 'octave.crespel@inria.fr'
MY_PASSWORD = '24-6391'
AGENDA_ITEMS_FILE = 'agenda_items.csv'

def read_agenda_items(file_name):
    with open(file_name, 'r', newline='') as f:
        reader = csv.DictReader(f)
        agenda_items = [dict(row) for row in reader]
    return agenda_items

def write_agenda_items(file_name, agenda_items):
    all_keys = sorted(list(set().union(*(it.keys() for it in agenda_items))))
    with open(file_name, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, all_keys)
        dict_writer.writeheader()
        dict_writer.writerows(agenda_items)

def scrape_agenda_items():
    # Go to Login Page
    driver = webdriver.Firefox()
    program_url = 'https://s2024.conference-program.org'
    login_url = f'{program_url}/wp-login.php'

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

    # List agenda items
    agenda_items = [{'html' : it.get_property('outerHTML')} for it in driver.find_elements(By.CSS_SELECTOR, '.agenda-item')]
    print(f"Found {len(agenda_items)} agenda items.")

    for i, it in enumerate(agenda_items):
        it['id'] = i
        soup = BeautifulSoup(it['html'], 'lxml')
        
        title_elems = soup.select('.title-speakers-td > a')
        if len(title_elems) == 0:
            title_elems = soup.select('.presentation-title > a')
            
        if len(title_elems) > 0:
            if 'href' in title_elems[0].attrs:
                full_url = program_url + '/' + title_elems[0].get('href')
                it['presentation_url'] = full_url
        print(f"Item {i} : url = ", it.get('presentation_url'))

    for i, it in enumerate(agenda_items):
        print(f"Scraping {i + 1} / {len(agenda_items)}")
        url = it.get('presentation_url')
        if url is not None:
            driver.get(url)

            try:
                vimeo_url = driver.find_element(By.ID, 'main_video').get_property('src')
            except NoSuchElementException as e:
                continue

            it['video_url'] = vimeo_url

    return agenda_items

def make_video_file_path(agenda_item):
    video_name = f"{agenda_item['title']} - {agenda_item['presenters']}".replace('/', '_')
    max_length = 200
    if len(video_name) > max_length:
        video_name = video_name[:max_length - 5] + '(...)'
    video_name = video_name + ".mp4"

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
        it['start_utc'] = start_utc
        it['end_utc'] = end_utc
        it['start_mdt'] = start_mdt
        it['end_mdt'] = end_mdt
        it['presenters'] = ';'.join(presenter_names)
        it['speakers'] = ';'.join(speaker_names)

        assert('Authors' not in title)
        assert('Contributors' not in title)

def download_videos(agenda_items):
    with YoutubeDL(params={'http_headers': {'Referer':'https://s2024.conference-program.org'}}) as ydl:
        for i, it in enumerate(agenda_items):
            print(f"Downloading video for item {i}/{len(agenda_items)}")
            
            video_file_path = make_video_file_path(it)
            if os.path.isfile(video_file_path):
                print(f"Video file '{video_file_path}' already exists.")
                it['video_file_path'] = video_file_path
            else:
                try:
                    if 'video_url' in it and len(it['video_url']) > 0:
                        info = ydl.extract_info(it['video_url'], download=False)
                        download_file_path = ydl.prepare_filename(info)
                        ydl.process_info(info)
                        it['video_file_path'] = video_file_path
                        os.rename(download_file_path, video_file_path)
                    else:
                        it['video_file_path'] = 'N/A'
                except Exception as e:
                    it['video_file_path'] = 'N/A'
                    print(e)

def generate_website(agenda_items):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates/'))

    file_names = ['index.html']
    for file_name in file_names:
        template = env.get_template(file_name)
        html = template.render({
            'agenda_items' : agenda_items,
        })

        with open(file_name, 'w') as f:
            f.write(html)

try:
    agenda_items = read_agenda_items(AGENDA_ITEMS_FILE)
except FileNotFoundError:
    agenda_items = scrape_agenda_items()

enrich_agenda_items(agenda_items)
# download_videos(agenda_items)
# write_agenda_items(AGENDA_ITEMS_FILE, agenda_items)

# write_agenda_items(AGENDA_ITEMS_FILE, agenda_items)
generate_website(agenda_items)
