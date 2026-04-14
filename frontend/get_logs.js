const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ headless: 'new' });
    const page = await browser.newPage();
    
    // Capture console messages
    page.on('console', msg => {
        console.log(`[PAGE LOG] ${msg.type().toUpperCase()}: ${msg.text()}`);
    });
    
    // Capture page errors
    page.on('pageerror', error => {
        console.error(`[PAGE ERROR]: ${error.message}`);
    });
    
    await page.goto('http://localhost:3000/isro', { waitUntil: 'load' });
    await new Promise(r => setTimeout(r, 2000));
    await browser.close();
})();
