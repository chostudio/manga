import { Component, EventEmitter, Output } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-search-bar',
  imports: [],
  templateUrl: './search-bar.html',
  styleUrl: './search-bar.css',
})
export class SearchBar {
  @Output() searchResults = new EventEmitter<any[]>();

  constructor(private http: HttpClient) {}

  onSearch(query: string) {
    if (!query.trim()) return;
    
    this.http.get<{panels: any[]}>('/search', { params: { q: query } })
      .subscribe({
        next: (response) => {
            console.log('Search response:', response);
            this.searchResults.emit(response.panels);
        },
        error: (error) => console.error('Search error:', error)
      });
  }
}
