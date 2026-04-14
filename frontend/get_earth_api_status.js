const puppeteer = require('puppeteer');

(async () => {
    try {
        const browser = await puppeteer.launch({ headless: 'new' });
        const page = await browser.newPage();
        
        page.on('request', request => {
            if (request.url().includes('api')) {
              console.log(`[REQUEST] ${request.method()} ${request.url()}`);
            }
        });

        page.on('response', response => {
            if (response.url().includes('api')) {
              console.log(`[RESPONSE] ${response.status()} ${response.url()}`);
            }
        });

        page.on('console', msg => {
            if (msg.type() === 'error' || msg.type() === 'warn') {
               console.log(`[PAGE ${msg.type().toUpperCase()}] ${msg.text()}`);
            }
        });

        await page.goto('http://localhost:3000/earth', { waitUntil: 'networkidle0' });
        await new Promise(r => setTimeout(r, 2000));
        
        await browser.close();
    } catch(err) {
        console.error(err);
    }
})();
