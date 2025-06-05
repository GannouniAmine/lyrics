import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

interface LyricsResponse {
  status: string;
  lyrics: string;
  metadata: {
    title: string;
    artist: string;
    thumbnail?: string;
  };
}

@Injectable({
  providedIn: 'root'
})
export class LyricsService {
  private apiUrl = 'https://lyrics-s7ko.onrender.com/api/extract';

  constructor(private http: HttpClient) { }

  getLyrics(youtubeUrl: string): Observable<LyricsResponse> {
    return this.http.post<LyricsResponse>(this.apiUrl, { youtube_url: youtubeUrl });
  }
}