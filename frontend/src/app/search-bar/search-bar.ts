import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-search-bar',
  imports: [],
  templateUrl: './search-bar.html',
  styleUrl: './search-bar.css',
})
export class SearchBar {
  constructor(private http: HttpClient) {}

  onSearch(query: string) {
    if (!query.trim()) return;
    
    this.http.get('http://localhost:8000/search', { params: { q: query } })
      .subscribe({
        next: (response) => console.log('Search response:', response),
        error: (error) => console.error('Search error:', error)
      });
  }
}
