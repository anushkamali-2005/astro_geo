const puppeteer = require('puppeteer');

(async () => {
    try {
        const browser = await puppeteer.launch({ headless: 'new' });
        const page = await browser.newPage();
        
        await page.goto('http://localhost:3000/isro', { waitUntil: 'networkidle2' });
        
        // Evaluate DOM inside <main>
        const html = await page.evaluate(() => {
            const main = document.querySelector('main');
            if (!main) return "No <main> tag found";
            return main.innerHTML;
        });
        
        console.log("MAIN CONTENT HTML:");
        console.log(html.substring(0, 5000)); // Print first 5k characters
        
        await browser.close();
    } catch(err) {
        console.error(err);
    }
})();
