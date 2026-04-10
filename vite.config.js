import { defineConfig } from 'vite';

export default defineConfig(({ mode }) => ({
    base: mode === 'production' ? '/research-papers/' : '/',
    root: '.',
    build: {
        outDir: 'dist',
        rollupOptions: {
            input: {
                main: 'index.html'
            }
        }
    },
    publicDir: 'public',
    server: {
        port: 3000
    }
}));
