// AdvisorNest — main.js
// Shared JavaScript across all pages

// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(function(flash) {
        setTimeout(function() {
            flash.style.opacity = '0';
            flash.style.transition = 'opacity 0.5s ease';
            setTimeout(function() {
                flash.remove();
            }, 500);
        }, 5000);
    });
});

// Update range slider value display
function updateRangeValue(input, displayId) {
    const display = document.getElementById(displayId);
    if (display) {
        display.textContent = input.value;
    }
}