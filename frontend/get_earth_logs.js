const puppeteer = require('puppeteer');

(async () => {
    try {
        const browser = await puppeteer.launch({ headless: 'new' });
        const page = await browser.newPage();
        
        page.on('console', msg => {
            console.log(`[PAGE LOG] ${msg.type().toUpperCase()}: ${msg.text()}`);
        });
        
        page.on('pageerror', error => {
            console.error(`[PAGE ERROR]: ${error.message}`);
        });

        page.on('requestfailed', request => {
          console.log(`[REQUEST FAILED] ${request.url()} - ${request.failure().errorText}`);
        });

        await page.goto('http://localhost:3000/earth', { waitUntil: 'networkidle2' });
        await new Promise(r => setTimeout(r, 3000));
        
        await browser.close();
    } catch(err) {
        console.error(err);
    }
})();
