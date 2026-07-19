import { Component } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { Inject } from '@angular/core';
import { SearchBar } from '../search-bar/search-bar';

interface PanelResult {
  id: number;
  chapter_id: string;
  page_index: number;
  panel_index: number;
  url: string;
  matched_via: string;
}

@Component({
  selector: 'app-home',
  imports: [CommonModule, SearchBar],
  templateUrl: './home.html',
  styleUrl: './home.css',
})
export class Home {
  panels: PanelResult[] = [];
  selectedPanel: PanelResult | null = null;

  constructor(@Inject(DOCUMENT) private document: Document) {}

  onSearchResults(results: PanelResult[]) {
    this.panels = results || [];
  }

  openPanel(panel: PanelResult) {
    this.selectedPanel = panel;
    this.document.body.style.overflow = 'hidden';
  }

  closePanel() {
    this.selectedPanel = null;
    this.document.body.style.overflow = '';
  }

  onOverlayClick(event: MouseEvent) {
    if ((event.target as HTMLElement).classList.contains('modal-overlay')) {
      this.closePanel();
    }
  }

  onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      this.closePanel();
    }
  }

  formatMatchedVia(matched_via: string): string {
    if (matched_via === 'panel') return 'Whole panel';
    if (matched_via === 'fallback') return 'Fallback (no embedding)';
    if (matched_via.startsWith('sub_element:')) {
      const label = matched_via.replace('sub_element:', '');
      return label.charAt(0).toUpperCase() + label.slice(1) + ' (sub-element)';
    }
    return matched_via;
  }
}
