import '@fontsource-variable/source-serif-4';
import '@fontsource-variable/source-serif-4/wght-italic.css';
import '@fontsource-variable/source-sans-3';
import { mount } from 'svelte';
import './styles/base.css';
import './styles/tooltip.css';
import App from './App.svelte';

mount(App, { target: document.getElementById('app')! });
