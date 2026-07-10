import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SearchBar } from '../search-bar/search-bar';

@Component({
  selector: 'app-home',
  imports: [CommonModule, SearchBar],
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home {
  panels: any[] = [];
  
  onSearchResults(results: any[]) {
    this.panels = results || [];
  }
}
