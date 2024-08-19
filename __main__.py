from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import os

from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
import time
import csv

MY_LOGIN = 'octave.crespel@inria.fr'
MY_PASSWORD = '24-6391'

def read_agenda_items(file_name):
    with open('agenda_items.csv', 'r', newline='') as f:
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

    for i, it in enumerate(agenda_items):
        it['id'] = i
        soup = BeautifulSoup(it['html'], 'lxml')
        urls = soup.select('td.title-speakers-td > a')
        if len(urls) > 0:
            if 'href' in urls[0].attrs:
                full_url = program_url + '/' + urls[0].get('href')
                print('url:', full_url)
                it['presentation_url'] = full_url

    for it in agenda_items:
        url = it.get('presentation_url')
        if url is not None:
            driver.get(url)

            try:
                vimeo_url = driver.find_element(By.ID, 'main_video').get_property('src')
            except NoSuchElementException as e:
                continue

            it['video_url'] = vimeo_url

    return agenda_items

def enrich_agenda_items(agenda_items):
    for i, it in enumerate(agenda_items):
        soup = BeautifulSoup(it['html'], 'lxml')
        start_time = soup.html.body.find('tr', recursive=False).attrs.get('s_utc', '')
        end_time = soup.html.body.find('tr', recursive=False).attrs.get('e_utc', '')

        presenter_divs = soup.select('.contributor .presenter-details, .author .presenter-details')
        presenter_names = [node.div.a.text for node in presenter_divs]
        
        speaker_divs = soup.select('.contributor .presenter-details.presenting, .author .presenter-details.presenting')
        speaker_names = [node.div.a.text for node in speaker_divs]

        print(i)
        title_elems = soup.select('.title-speakers-td > a')
        if len(title_elems) == 0:
            title_elems = soup.select('.title-speakers-td')
        if len(title_elems) == 0:
            title_elems = soup.select('.presentation-title')
        title = title_elems[0].text

        it['title'] = title
        it['start_time'] = start_time
        it['end_time'] = end_time
        it['presenters'] = ';'.join(presenter_names)
        it['speakers'] = ';'.join(speaker_names)

        assert('Authors' not in title)
        assert('Contributors' not in title)

        print(title, start_time, end_time, presenter_names, speaker_names, sep='\n')
        print()


def download_videos(agenda_items):
    with YoutubeDL(params={'http_headers': {'Referer':'https://s2024.conference-program.org'}}) as ydl:
        for i, it in enumerate(agenda_items):
            print(f"Item {i}/{len(agenda_items)}")
            if 'video_file_path' not in it or len(it['video_file_path']) == 0:
                try:
                    if 'video_url' in it and len(it['video_url']) > 0:
                        info = ydl.extract_info(it['video_url'], download=False)
                        file_path = ydl.prepare_filename(info)
                        it['video_file_path'] = file_path
                except Exception as e:
                    it['video_file_path'] = 'N/A'
                    print(e)

        write_agenda_items('agenda_items.csv', agenda_items)

        for i, it in enumerate(agenda_items):
            print(f"Starting download {i}/{len(agenda_items)}")
            url = it.get('video_url')
            if url is not None and len(url) > 0:
                try:
                    ydl.download(it['video_url'])
                except Exception as e:
                    print(e)

def rename_videos(agenda_items):
    for it in agenda_items:
        old_video_path = it['video_file_path']
        if old_video_path != '' and old_video_path != 'N/A':
            new_video_name = f"{it['title']} - {it['presenters']}".replace('/', '_')
            max_length = 200
            if len(new_video_name) > max_length:
                new_video_name = new_video_name[:max_length - 5] + '(...)'
            new_video_name = new_video_name + ".mp4"

            new_video_path = 'videos/' + new_video_name
            
            it['video_file_path'] = new_video_path
            try:
                os.rename(old_video_path, new_video_path)
            except FileNotFoundError as e:
                print(e)
            except Exception as e:
                print(e)

try:
    agenda_items = read_agenda_items('agenda_items.csv')
except FileNotFoundError:
    agenda_items = scrape_agenda_items()

rename_videos(agenda_items)

write_agenda_items('agenda_items.csv', agenda_items)
