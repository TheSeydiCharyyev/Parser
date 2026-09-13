/**
 * Language switcher for HTML/CSS Essentials course
 * Supports: Russian (ru) and English (en)
 * Saves preference to localStorage
 */

function setLang(lang) {
    // Hide/show elements with data-lang attribute
    document.querySelectorAll('[data-lang]').forEach(function(el) {
        if (el.dataset.lang === lang) {
            el.classList.remove('lang-hidden');
        } else {
            el.classList.add('lang-hidden');
        }
    });

    // Update html lang attribute
    document.documentElement.lang = lang;

    // Save preference
    localStorage.setItem('htmlcss-lang', lang);

    // Update all lang buttons
    document.querySelectorAll('.lang-btn').forEach(function(btn) {
        btn.textContent = lang === 'ru' ? 'EN' : 'RU';
    });
}

function toggleLang() {
    var current = localStorage.getItem('htmlcss-lang') || 'ru';
    setLang(current === 'ru' ? 'en' : 'ru');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    var lang = localStorage.getItem('htmlcss-lang') || 'ru';
    setLang(lang);
});
