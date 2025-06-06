import yt_dlp
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
import xml.etree.ElementTree as ET
import json
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="lycrissnap API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Modèles Pydantic
class ExtractRequest(BaseModel):
    youtube_url: str

class LyricsResponse(BaseModel):
    status: str
    lyrics: str
    metadata: dict

def clean_title(title):
    """Nettoie le titre pour une meilleure recherche"""
    replacements = [
        '(Official Music Video)', '(Official Video)', '(Music Video)',
        '(Official)', '(Lyrics)', '[Official Video]', '[Music Video]',
        '[Official]', '[Lyrics]', '| Official Video', '- Official Video',
        '(Clip officiel)', '[Clip officiel]', '- Clip officiel',
        '[Clip Officiel]', '(Clip Officiel)', 'prod by', 'prod. by',
        'produced by', 'ft.', 'feat.', 'featuring',
        '[One Take Video]', '(One Take Video)', '[One Take]', '(One Take)',
        'Remix', 'Mix', 'Cover', 'Version'
    ]
    
    cleaned = title
    for replacement in replacements:
        cleaned = re.sub(re.escape(replacement), '', cleaned, flags=re.IGNORECASE).strip()
    
    # Remove quotes and extra brackets/parentheses content
    cleaned = re.sub(r'["\']', '', cleaned)
    cleaned = re.sub(r'\[.*?\]', '', cleaned)
    cleaned = re.sub(r'\(.*?\)', '', cleaned)
    
    # Remove extra whitespace and clean up
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned

def parse_artist_and_title(youtube_title, uploader):
    """Parse artist and title from YouTube metadata"""
    title = clean_title(youtube_title)
    
    # Check for common collaboration patterns
    patterns = [
        r'^(.+?)\s*,\s*(.+?)\s*[-–]\s*(.+)$',  # "Artist1, Artist2 - Title"
        r'^(.+?)\s*&\s*(.+?)\s*[-–]\s*(.+)$',  # "Artist1 & Artist2 - Title"
        r'^(.+?)\s*[-–]\s*(.+)$',              # "Artist - Title"
        r'^(.+?)\s*[\(\[]?ft\.?\s*(.+?)[\)\]]?\s*[-–]\s*(.+)$',  # "Artist ft. Artist2 - Title"
    ]
    
    for pattern in patterns:
        match = re.match(pattern, title, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 3:  # Artist1, Artist2, Title
                artist = f"{groups[0].strip()}, {groups[1].strip()}"
                song_title = groups[2].strip()
                return artist, song_title
            elif len(groups) == 2:  # Artist, Title
                artist = groups[0].strip()
                song_title = groups[1].strip()
                return artist, song_title
    
    # If no pattern matches, use uploader as artist and full title as song
    return uploader, title

def get_metadata(youtube_url):
    """Récupère les métadonnées de la vidéo YouTube"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_url, download=False)
            youtube_title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown Artist')
            artist, title = parse_artist_and_title(youtube_title, uploader)
            return title, artist
        except Exception as e:
            print(f"❌ Erreur lors de l'extraction des métadonnées: {e}")
            return "Unknown Title", "Unknown Artist"

def get_lyrics_ovh(artist, title):
    """Utilise l'API lyrics.ovh (gratuite)"""
    try:
        print(f"🔍 Recherche sur Lyrics.ovh: {artist} - {title}")
        url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
            'Referer': 'https://lyrics.ovh/'
        }
        
        # Add delay to avoid rate limiting
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics', '')
            if lyrics and lyrics.strip() and not lyrics.startswith("Pardon"):
                return lyrics.strip()
            else:
                print("❌ Paroles vides ou non trouvées sur Lyrics.ovh")
        elif response.status_code == 404:
            print("❌ Chanson non trouvée sur Lyrics.ovh")
        else:
            print(f"⚠️ Erreur Lyrics.ovh (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️ Erreur Lyrics.ovh: {e}")
    
    return None

def get_lyrics_musixmatch_search(artist, title):
    """Recherche sur Musixmatch via scraping avec headers améliorés"""
    try:
        print(f"🔍 Recherche sur Musixmatch: {artist} - {title}")
        
        # Use direct lyrics URL format instead of search
        artist_clean = re.sub(r'[^a-zA-Z0-9\s]', '', artist).lower().replace(' ', '-')
        title_clean = re.sub(r'[^a-zA-Z0-9\s]', '', title).lower().replace(' ', '-')
        
        # Try direct URL format
        direct_url = f"https://www.musixmatch.com/lyrics/{artist_clean}/{title_clean}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0'
        }
        
        # Add session with longer delay
        session = requests.Session()
        session.headers.update(headers)
        time.sleep(3)  # Longer delay
        
        try:
            response = session.get(direct_url, timeout=20, allow_redirects=True)
            
            if response.status_code == 200:
                return scrape_musixmatch_lyrics_from_response(response.text)
            elif response.status_code == 403:
                print("⚠️ Musixmatch bloque les requêtes automatisées (HTTP 403)")
            elif response.status_code == 404:
                print("❌ Chanson non trouvée sur Musixmatch (HTTP 404)")
            else:
                print(f"⚠️ Erreur Musixmatch (HTTP {response.status_code})")
        except requests.exceptions.Timeout:
            print("⚠️ Timeout Musixmatch - site trop lent")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erreur de connexion Musixmatch: {e}")
            
    except Exception as e:
        print(f"⚠️ Erreur Musixmatch search: {e}")
    
    return None

def scrape_musixmatch_lyrics_from_response(html_content):
    """Scrape les paroles depuis le contenu HTML de Musixmatch"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Chercher les paroles dans différents conteneurs possibles
        lyrics_selectors = [
            'p[class*="lyrics__content"]',
            'span[class*="lyrics__content"]', 
            'div[class*="lyrics"]',
            'p[data-test="lyrics-text"]',
            'div[class*="mxm-lyrics"]',
            'span[class*="lyrics__content__ok"]'
        ]
        
        for selector in lyrics_selectors:
            lyrics_elements = soup.select(selector)
            if lyrics_elements:
                lyrics = '\n'.join([elem.get_text().strip() for elem in lyrics_elements])
                if lyrics and len(lyrics) > 50:  # Vérifier que ce sont de vraies paroles
                    return lyrics
        
        # Try alternative approach - look for JSON-LD data
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if 'lyrics' in data:
                    return data['lyrics']
            except:
                continue
        
        print("❌ Structure de paroles Musixmatch non reconnue")
    except Exception as e:
        print(f"⚠️ Erreur scraping Musixmatch: {e}")
    
    return None

def scrape_musixmatch_lyrics(url):
    """Scrape les paroles d'une page Musixmatch"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Chercher les paroles dans différents conteneurs possibles
            lyrics_selectors = [
                'p[class*="lyrics__content"]',
                'span[class*="lyrics__content"]',
                'div[class*="lyrics"]',
                'p[data-test="lyrics-text"]'
            ]
            
            for selector in lyrics_selectors:
                lyrics_elements = soup.select(selector)
                if lyrics_elements:
                    lyrics = '\n'.join([elem.get_text().strip() for elem in lyrics_elements])
                    if lyrics and len(lyrics) > 50:  # Vérifier que ce sont de vraies paroles
                        return lyrics
            
            print("❌ Structure de paroles Musixmatch non reconnue")
        else:
            print(f"⚠️ Erreur scraping Musixmatch (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️ Erreur scraping Musixmatch: {e}")
    
    return None

def get_lyrics_azlyrics(artist, title):
    """Recherche sur AZLyrics avec amélioration de l'URL cleaning"""
    try:
        print(f"🔍 Recherche sur AZLyrics: {artist} - {title}")
        
        # Nettoyer l'artiste et le titre pour AZLyrics plus intelligemment
        def clean_for_azlyrics(text):
            # Remove common prefixes like "the"
            if text.lower().startswith('the '):
                text = text[4:]
            # Remove everything that's not alphanumeric
            return re.sub(r'[^a-zA-Z0-9]', '', text.lower())
        
        clean_artist = clean_for_azlyrics(artist)
        clean_title = clean_for_azlyrics(title)
        
        # Try multiple URL variations
        urls_to_try = [
            f"https://www.azlyrics.com/lyrics/{clean_artist}/{clean_title}.html",
            # Try with just first artist if collaboration
            f"https://www.azlyrics.com/lyrics/{clean_for_azlyrics(artist.split(',')[0])}/{clean_title}.html" if ',' in artist else None,
            # Try without common words
            f"https://www.azlyrics.com/lyrics/{clean_artist}/{clean_for_azlyrics(title.split()[0])}.html" if len(title.split()) > 1 else None
        ]
        
        # Filter out None values
        urls_to_try = [url for url in urls_to_try if url]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'max-age=0'
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        for url in urls_to_try:
            try:
                print(f"🔗 Tentative URL: {url}")
                time.sleep(3)  # Longer delay for AZLyrics
                
                response = session.get(url, timeout=20, allow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Multiple selectors for AZLyrics content
                    lyrics_selectors = [
                        'div:not([class]):not([id])',  # Main lyrics div without class/id
                        'div[class=""]',               # Empty class div
                        'div.col-xs-12.col-lg-8.text-center div:not([class]):not([id])',
                        'div.ringtone + div:not([class]):not([id])'
                    ]
                    
                    for selector in lyrics_selectors:
                        lyrics_divs = soup.select(selector)
                        for lyrics_div in lyrics_divs:
                            if lyrics_div and lyrics_div.get_text().strip():
                                lyrics_text = lyrics_div.get_text().strip()
                                # Check if this looks like actual lyrics (reasonable length, not navigation)
                                if (len(lyrics_text) > 100 and 
                                    'Submit Corrections' not in lyrics_text and
                                    'Thanks to' not in lyrics_text[:50]):
                                    return lyrics_text
                    
                    print(f"❌ Paroles non trouvées à l'URL: {url}")
                elif response.status_code == 404:
                    print(f"❌ Page non trouvée (404): {url}")
                elif response.status_code == 403:
                    print(f"⚠️ Accès refusé par AZLyrics (403): {url}")
                else:
                    print(f"⚠️ Erreur HTTP {response.status_code}: {url}")
                    
            except requests.exceptions.Timeout:
                print(f"⚠️ Timeout pour: {url}")
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Erreur de connexion pour {url}: {e}")
            except Exception as e:
                print(f"⚠️ Erreur inattendue pour {url}: {e}")
                
    except Exception as e:
        print(f"⚠️ Erreur AZLyrics: {e}")
    
    return None

def search_google_lyrics(artist, title):
    """Recherche Google pour trouver des sites de paroles avec meilleure logique"""
    try:
        print(f"🔍 Recherche Google: {artist} - {title} lyrics")
        
        # Recherche Google avec des sites spécifiques - plus ciblée
        queries = [
            f'"{artist}" "{title}" lyrics site:genius.com',
            f'"{artist}" "{title}" lyrics',
            f'{artist} {title} lyrics site:azlyrics.com',
            f'{artist} {title} song lyrics'
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        for i, query in enumerate(queries):
            try:
                print(f"📱 Essai Google {i+1}/4: {query[:50]}...")
                
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                time.sleep(2)  # Délai respectueux
                
                response = session.get(search_url, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Chercher les liens dans les résultats avec plusieurs sélecteurs
                    link_selectors = [
                        'a[href*="/url?q="]',
                        'h3 a',
                        'div.yuRUbf a'
                    ]
                    
                    found_links = []
                    for selector in link_selectors:
                        links = soup.select(selector)
                        found_links.extend(links)
                    
                    for link in found_links:
                        href = link.get('href', '')
                        if '/url?q=' in href:
                            try:
                                actual_url = href.split('/url?q=')[1].split('&')[0]
                                actual_url = urllib.parse.unquote(actual_url)
                                
                                # Filtrer les sites de paroles connus
                                target_sites = [
                                    'genius.com/lyrics',
                                    'azlyrics.com/lyrics',
                                    'musixmatch.com/lyrics',
                                    'lyrics.com',
                                    'metrolyrics.com'
                                ]
                                
                                if any(site in actual_url.lower() for site in target_sites):
                                    print(f"🔗 Lien prometteur trouvé: {actual_url[:80]}...")
                                    
                                    # Essayer de scraper selon le site
                                    if 'genius.com' in actual_url:
                                        lyrics = scrape_genius_page(actual_url)
                                        if lyrics and len(lyrics) > 100:
                                            return lyrics
                                    elif 'azlyrics.com' in actual_url:
                                        lyrics = scrape_azlyrics_direct(actual_url)
                                        if lyrics and len(lyrics) > 100:
                                            return lyrics
                                    elif 'musixmatch.com' in actual_url:
                                        lyrics = scrape_musixmatch_lyrics(actual_url)
                                        if lyrics and len(lyrics) > 100:
                                            return lyrics
                            except Exception as url_error:
                                print(f"⚠️ Erreur traitement URL: {url_error}")
                                continue
                
                elif response.status_code == 429:
                    print("⚠️ Google rate limiting - attente plus longue")
                    time.sleep(5)
                else:
                    print(f"⚠️ Google search error (HTTP {response.status_code})")
                    
            except requests.exceptions.Timeout:
                print(f"⚠️ Timeout Google search query {i+1}")
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Erreur connexion Google query {i+1}: {e}")
            except Exception as e:
                print(f"⚠️ Erreur Google query {i+1}: {e}")
                continue
    
    except Exception as e:
        print(f"⚠️ Erreur générale Google search: {e}")
    
    print("❌ Aucun résultat exploitable trouvé via Google")
    return None

def scrape_genius_page(url):
    """Scrape une page Genius directement"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Chercher les différents conteneurs de paroles sur Genius
            lyrics_selectors = [
                'div[class*="Lyrics__Container"]',
                'div[data-lyrics-container="true"]',
                'div[class*="lyrics"]'
            ]
            
            for selector in lyrics_selectors:
                lyrics_containers = soup.select(selector)
                if lyrics_containers:
                    lyrics_text = []
                    for container in lyrics_containers:
                        # Extraire le texte en préservant les sauts de ligne
                        for br in container.find_all('br'):
                            br.replace_with('\n')
                        lyrics_text.append(container.get_text())
                    
                    if lyrics_text:
                        combined_lyrics = '\n'.join(lyrics_text).strip()
                        if len(combined_lyrics) > 50:
                            return combined_lyrics
            
            print("❌ Structure de paroles Genius non reconnue")
        else:
            print(f"⚠️ Erreur scraping Genius (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️ Erreur scraping Genius: {e}")
    
    return None

def scrape_azlyrics_direct(url):
    """Scrape une page AZLyrics directement depuis une URL donnée"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        time.sleep(3)  # Respectful delay
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Multiple selectors for AZLyrics content
            lyrics_selectors = [
                'div:not([class]):not([id])',  # Main lyrics div without class/id
                'div[class=""]',               # Empty class div
                'div.col-xs-12.col-lg-8.text-center div:not([class]):not([id])',
                'div.ringtone + div:not([class]):not([id])'
            ]
            
            for selector in lyrics_selectors:
                lyrics_divs = soup.select(selector)
                for lyrics_div in lyrics_divs:
                    if lyrics_div and lyrics_div.get_text().strip():
                        lyrics_text = lyrics_div.get_text().strip()
                        # Check if this looks like actual lyrics
                        if (len(lyrics_text) > 100 and 
                            'Submit Corrections' not in lyrics_text and
                            'Thanks to' not in lyrics_text[:50] and
                            'Sorry' not in lyrics_text[:20]):
                            return lyrics_text
            
            print(f"❌ Paroles non trouvées à l'URL: {url}")
        else:
            print(f"⚠️ Erreur scraping AZLyrics direct (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️ Erreur scraping AZLyrics direct: {e}")
    
    return None

def get_video_info_youtube(youtube_url):
    """Récupère les informations détaillées de la vidéo YouTube incluant la miniature"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_url, download=False)
            youtube_title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown Artist')
            thumbnail = info.get('thumbnail', '')
            
            artist, title = parse_artist_and_title(youtube_title, uploader)
            return title, artist, thumbnail
        except Exception as e:
            print(f"❌ Erreur lors de l'extraction des métadonnées: {e}")
            return "Unknown Title", "Unknown Artist", ""

def create_search_variations(title, artist):
    """Crée différentes variations de recherche pour améliorer les chances de trouver des paroles"""
    variations = [(artist, title)]
    
    # Variations pour les collaborations
    if ',' in artist:
        artists = [a.strip() for a in artist.split(',')]
        variations.append((artists[0], title))  # Premier artiste seulement
        if len(artists) > 1:
            variations.append((f"{artists[0]} feat {artists[1]}", title))
    
    # Variations pour feat/ft
    if any(word in artist.lower() for word in ['feat', 'ft.', 'featuring']):
        main_artist = re.split(r'\s+(?:feat\.?|ft\.?|featuring)\s+', artist, flags=re.IGNORECASE)[0].strip()
        variations.append((main_artist, title))
    
    # Variations de titre simplifiées
    simple_title = re.sub(r'\[.*?\]|\(.*?\)', '', title).strip()
    if simple_title != title and simple_title:
        variations.append((artist, simple_title))
    
    # Titre sans mots courants
    clean_title_words = re.sub(r'\b(?:remix|mix|version|edit|remaster|remastered|cover)\b', '', title, flags=re.IGNORECASE).strip()
    if clean_title_words != title and clean_title_words:
        variations.append((artist, clean_title_words))
    
    # Premiers mots du titre si long
    title_words = title.split()
    if len(title_words) > 3:
        short_title = ' '.join(title_words[:3])
        variations.append((artist, short_title))
    
    return variations

def main():
    print("🎵 RÉCUPÉRATEUR DE PAROLES YOUTUBE 🎵")
    print("="*50)
    
    youtube_url = input("🔗 Entrez l'URL YouTube de la chanson : ").strip()
    
    if not youtube_url:
        print("❌ URL vide. Au revoir !")
        return
    
    # Récupérer les métadonnées
    print("\n📡 Récupération des informations...")
    title, artist = get_metadata(youtube_url)
    print(f"\n🎵 Titre : {title}")
    print(f"👤 Artiste : {artist}")
    
    # Nettoyer encore plus le titre
    clean_title_for_search = clean_title(title)
    
    # Éviter la duplication de l'artiste dans le titre
    if artist.lower() in clean_title_for_search.lower():
        clean_title_for_search = clean_title_for_search.replace(artist, '').strip(' -')
    
    print(f"🔍 Recherche pour : {artist} - {clean_title_for_search}")
    
    lyrics = None
    
    # Try multiple search variations with improved logic
    search_variations = [
        (artist, clean_title_for_search),
    ]
    
    # Special handling for covers/remixes - try original song info
    original_song_match = re.search(r'([^"]+)\s*["\']([^"\'\.]+)["\']', title)
    if original_song_match:
        potential_original_artist = original_song_match.group(1).strip()
        potential_original_title = original_song_match.group(2).strip()
        print(f"🎵 Détection possible de cover/remix: {potential_original_artist} - {potential_original_title}")
        # Try the original song first, then the cover artist version
        search_variations.insert(0, (potential_original_artist, potential_original_title))
        search_variations.append((artist, potential_original_title))
    
    # Add variations for collaborations
    if ',' in artist:
        artists = [a.strip() for a in artist.split(',')]
        # Try with just the first artist
        search_variations.append((artists[0], clean_title_for_search))
        # Try with "feat" format if more than one artist
        if len(artists) > 1:
            search_variations.append((f"{artists[0]} feat {artists[1]}", clean_title_for_search))
    
    # Handle "feat", "ft", "featuring" in artist name
    if any(word in artist.lower() for word in ['feat', 'ft.', 'featuring']):
        # Extract main artist before "feat"/"ft"/"featuring"
        main_artist = re.split(r'\s+(?:feat\.?|ft\.?|featuring)\s+', artist, flags=re.IGNORECASE)[0].strip()
        search_variations.append((main_artist, clean_title_for_search))
    
    # Add variations with simplified titles
    simple_title = re.sub(r'\[.*?\]|\(.*?\)', '', clean_title_for_search).strip()
    if simple_title != clean_title_for_search and simple_title:
        search_variations.append((artist, simple_title))
    
    # Try removing common words from title
    title_clean = re.sub(r'\b(?:remix|mix|version|edit|remaster|remastered|cover)\b', '', clean_title_for_search, flags=re.IGNORECASE).strip()
    if title_clean != clean_title_for_search and title_clean:
        search_variations.append((artist, title_clean))
    
    # For complex titles, try extracting key phrases
    if 'still' in clean_title_for_search.lower() and 'dre' in clean_title_for_search.lower():
        search_variations.append(("Dr. Dre", "Still D.R.E."))
        search_variations.append((artist, "Still D.R.E."))
    
    # Try just the first few words of the title if it's long
    title_words = clean_title_for_search.split()
    if len(title_words) > 3:
        short_title = ' '.join(title_words[:3])
        search_variations.append((artist, short_title))
    elif len(title_words) > 1:
        search_variations.append((artist, title_words[0]))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for variation in search_variations:
        if variation not in seen and variation[0] and variation[1]:  # Ensure both artist and title exist
            seen.add(variation)
            unique_variations.append(variation)
    search_variations = unique_variations[:8]  # Increase to 8 variations max
    
    for i, (search_artist, search_title) in enumerate(search_variations):
        if lyrics:
            break
            
        print(f"\n🎯 Variation de recherche {i+1}: {search_artist} - {search_title}")
        
        # Méthode 1: Lyrics.ovh (API gratuite)
        print("\n🔄 Tentative 1/4: Lyrics.ovh")
        lyrics = get_lyrics_ovh(search_artist, search_title)
        
        # Méthode 2: Musixmatch scraping
        if not lyrics:
            print("\n🔄 Tentative 2/4: Musixmatch")
            lyrics = get_lyrics_musixmatch_search(search_artist, search_title)
        
        # Méthode 3: AZLyrics
        if not lyrics:
            print("\n🔄 Tentative 3/4: AZLyrics")
            lyrics = get_lyrics_azlyrics(search_artist, search_title)
        
        # Méthode 4: Recherche Google
        if not lyrics:
            print("\n🔄 Tentative 4/4: Recherche Google")
            lyrics = search_google_lyrics(search_artist, search_title)
        
        # If found lyrics, break the loop
        if lyrics:
            break
    
    # Afficher le résultat
    print("\n" + "="*50)
    print("📝 PAROLES :")
    print("="*50)
    
    if lyrics and lyrics.strip():
        print(lyrics)
        print("\n✅ Paroles trouvées avec succès !")
    else:
        print("❌ Désolé, aucune parole n'a pu être trouvée.")
        print("💡 Suggestions :")
        print("   - Vérifiez l'orthographe du titre et de l'artiste")
        print("   - Essayez avec une autre vidéo de la même chanson")
        print("   - Cette chanson pourrait ne pas avoir de paroles disponibles en ligne")

# Endpoint API pour extraire les paroles
@app.post("/api/extract", response_model=LyricsResponse)
async def extract_lyrics(request: ExtractRequest):
    try:
        youtube_url = request.youtube_url
        
        if not youtube_url or "youtube.com" not in youtube_url and "youtu.be" not in youtube_url:
            return LyricsResponse(
                status="error",
                lyrics="URL YouTube invalide",
                metadata={"title": "", "artist": ""}
            )
        
        # Extraire le titre et l'artiste depuis YouTube
        title, artist, thumbnail = get_video_info_youtube(youtube_url)
        
        if not title:
            return LyricsResponse(
                status="error",
                lyrics="Impossible d'extraire les informations de la vidéo",
                metadata={"title": "", "artist": ""}
            )
        
        # Nettoyer le titre
        clean_song_title = clean_title(title)
        print(f"\n🎵 Titre original: {title}")
        print(f"🎵 Titre nettoyé: {clean_song_title}")
        print(f"🎤 Artiste: {artist}")
        
        # Créer les variations de recherche
        variations = create_search_variations(clean_song_title, artist)
        
        # Éliminer les doublons
        seen = set()
        unique_variations = []
        for variation in variations:
            variation_key = f"{variation[0].lower()} - {variation[1].lower()}"
            if variation_key not in seen:
                seen.add(variation)
                unique_variations.append(variation)
        search_variations = unique_variations[:8]
        
        lyrics = ""
        for i, (search_artist, search_title) in enumerate(search_variations):
            if lyrics:
                break
                
            print(f"\n🎯 Variation de recherche {i+1}: {search_artist} - {search_title}")
            
            # Méthode 1: Lyrics.ovh
            lyrics = get_lyrics_ovh(search_artist, search_title)
            
            # Méthode 2: Musixmatch scraping
            if not lyrics:
                lyrics = get_lyrics_musixmatch_search(search_artist, search_title)
            
            # Méthode 3: AZLyrics
            if not lyrics:
                lyrics = get_lyrics_azlyrics(search_artist, search_title)
            
            # Méthode 4: Recherche Google
            if not lyrics:
                lyrics = search_google_lyrics(search_artist, search_title)
            
            if lyrics:
                break
        
        if lyrics and lyrics.strip():
            return LyricsResponse(
                status="success",
                lyrics=lyrics,
                metadata={
                    "title": clean_song_title,
                    "artist": artist,
                    "thumbnail": thumbnail
                }
            )
        else:
            return LyricsResponse(
                status="error",
                lyrics="Aucune parole trouvée pour cette chanson",
                metadata={
                    "title": clean_song_title,
                    "artist": artist,
                    "thumbnail": thumbnail
                }
            )
            
    except Exception as e:
        print(f"Erreur lors de l'extraction: {str(e)}")
        return LyricsResponse(
            status="error",
            lyrics=f"Erreur: {str(e)}",
            metadata={"title": "", "artist": ""}
        )

# Endpoint pour tester l'API
@app.get("/")
async def root():
    return {"message": "lycrissnap API is running!"}

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Fix encoding for Windows console
    if sys.platform == "win32":
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    
    print("Demarrage du serveur API sur http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
