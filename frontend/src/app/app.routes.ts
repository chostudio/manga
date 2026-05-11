import { Routes } from '@angular/router';
import { Home } from './home/home';
import { Upload } from './upload/upload';

export const routes: Routes = [
  { path: '', component: Home },
  { path: 'upload', component: Upload },
];
