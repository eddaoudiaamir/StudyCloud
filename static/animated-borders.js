// Wrap inputs and buttons with animated border wrappers
document.addEventListener('DOMContentLoaded', function() {
    
    // Wrap all form inputs
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], select, textarea');
    
    inputs.forEach(input => {
        // Skip if already wrapped
        if (input.closest('.input-animated-wrapper')) return;
        
        // Skip search input in navbar (already styled differently)
        if (input.classList.contains('search-input')) return;
        
        const wrapper = document.createElement('div');
        wrapper.className = 'input-animated-wrapper';
        
        // Get parent width if input has full width
        const inputWidth = input.style.width || getComputedStyle(input).width;
        if (inputWidth) {
            wrapper.style.width = inputWidth;
        }
        
        // Wrap the input
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
    });
    
    // Wrap primary buttons (not all nav buttons)
    const buttons = document.querySelectorAll('.btn-primary, .submit-btn, button[type="submit"]');
    
    buttons.forEach(button => {
        // Skip if already wrapped
        if (button.closest('.btn-animated-wrapper')) return;
        
        // Skip nav buttons and tab buttons
        if (button.classList.contains('nav-btn') || button.classList.contains('tab-btn') || button.classList.contains('card-btn')) return;
        
        const wrapper = document.createElement('div');
        wrapper.className = 'btn-animated-wrapper';
        
        // Wrap the button
        button.parentNode.insertBefore(wrapper, button);
        wrapper.appendChild(button);
    });
});
