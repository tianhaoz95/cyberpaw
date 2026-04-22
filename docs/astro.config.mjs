// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://tianhaoz95.github.io',
  base: '/cyberpaw',
  integrations: [
    starlight({
      title: 'CyberPaw Docs',
      description: 'Developer documentation for CyberPaw',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/tianhaoz95/cyberpaw' },
      ],
      sidebar: [
        { label: 'Introduction', link: '/intro' },
        {
          label: 'Getting Started',
          items: [
            { label: 'Installation', link: '/getting-started/installation' },
            { label: 'Running the App', link: '/getting-started/running' },
            { label: 'Loading a Model', link: '/getting-started/models' },
          ],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', link: '/architecture/overview' },
            { label: 'Sidecar Protocol', link: '/architecture/protocol' },
            { label: 'Agent Harness', link: '/architecture/agent' },
            { label: 'LLM Backends', link: '/architecture/backends' },
          ],
        },
        {
          label: 'Tools',
          items: [
            { label: 'Tool System', link: '/tools/overview' },
            { label: 'File Tools', link: '/tools/file' },
            { label: 'Execution Tools', link: '/tools/execution' },
            { label: 'Web Tools', link: '/tools/web' },
            { label: 'Agent Tools', link: '/tools/agent' },
          ],
        },
        {
          label: 'Frontend',
          items: [
            { label: 'Components', link: '/frontend/components' },
            { label: 'IPC Bridge', link: '/frontend/ipc' },
          ],
        },
        { label: 'Contributing', link: '/contributing' },
      ],
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});
