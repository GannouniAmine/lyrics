import { Component } from '@angular/core';
import { LyricsService } from '../services/lyrics.service';

interface LyricsResponse {
  status: string;
  lyrics: string;
  metadata: {
    title: string;
    artist: string;
    thumbnail?: string;
  };
}

@Component({
  selector: 'app-pageprincipale',
  templateUrl: './pageprincipale.component.html',
  styleUrls: ['./pageprincipale.component.css']
})
export class PageprincipaleComponent {
  youtubeUrl = '';
  lyrics = '';
  isLoading = false;
  errorMessage = '';
  songInfo: { title: string; artist: string; thumbnail?: string } | null = null;
  selectedLang = 'fr';
  translatedLyrics = '';

  constructor(private lyricsService: LyricsService) {}

  fetchLyrics() {
    if (!this.youtubeUrl) return;
    
    this.isLoading = true;
    this.errorMessage = '';
    
    this.lyricsService.getLyrics(this.youtubeUrl).subscribe({
      next: (response: LyricsResponse) => {
        this.lyrics = response.lyrics;
        this.songInfo = response.metadata;
        this.isLoading = false;
      },
      error: (err: any) => {
        this.errorMessage = 'Failed to get lyrics. Please try another song.';
        this.isLoading = false;
        console.error(err);
      }
    });
  }

  copyLyrics() {
    if (this.lyrics) {
      navigator.clipboard.writeText(this.lyrics);
    }
  }
}