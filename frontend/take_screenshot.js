const puppeteer = require('puppeteer');

(async () => {
    try {
        const browser = await puppeteer.launch({ headless: 'new' });
        const page = await browser.newPage();
        
        await page.setViewport({ width: 1400, height: 900 });
        await page.goto('http://localhost:3000/isro', { waitUntil: 'networkidle0' });
        await page.screenshot({ path: 'screenshot.png' });
        console.log('Screenshot saved to screenshot.png');
        await browser.close();
    } catch(err) {
        console.error(err);
    }
})();
