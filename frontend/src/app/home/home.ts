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
  score: number;
  similarity: number;
  matched_tags: string[];
  matched_labels: string[];
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
    if (matched_via === 'tag') return 'Tag match';
    if (matched_via === 'sub_element') return 'Detected element';
    if (matched_via === 'vibes') return 'Vibes (CLIP)';
    return matched_via;
  }

  formatSimilarity(similarity: number): string {
    return Math.round(similarity * 100) + '%';
  }

  formatScore(score: number): string {
    return Math.round(Math.min(1, score) * 100) + '%';
  }

  formatMatchedLabels(labels: string[]): string {
    if (!labels || labels.length === 0) return '';
    return labels.map(l => l.charAt(0).toUpperCase() + l.slice(1)).join(', ');
  }
}
