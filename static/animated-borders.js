// Wrap inputs and buttons with animated border layers
document.addEventListener('DOMContentLoaded', function() {
    
    // Wrap all inputs
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], .search-input, select, textarea');
    
    inputs.forEach(input => {
        if (!input.closest('.input-animated-wrapper')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'input-animated-wrapper';
            
            // Create border layers
            const glow = document.createElement('div');
            glow.className = 'glow-input';
            
            const darkBorder = document.createElement('div');
            darkBorder.className = 'darkBorderBg-input';
            
            const border = document.createElement('div');
            border.className = 'border-input';
            
            // Wrap input
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(glow);
            wrapper.appendChild(darkBorder);
            wrapper.appendChild(border);
            wrapper.appendChild(input);
        }
    });
    
    // Wrap all buttons
    const buttons = document.querySelectorAll('.btn, .btn-primary, .btn-secondary, .btn-danger, .submit-btn, button[type="submit"]');
    
    buttons.forEach(button => {
        if (!button.closest('.btn-animated-wrapper') && !button.classList.contains('nav-btn') && !button.classList.contains('tab-btn')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'btn-animated-wrapper';
            wrapper.style.display = 'inline-block';
            
            // Create border layers
            const glow = document.createElement('div');
            glow.className = 'glow-btn';
            
            const darkBorder = document.createElement('div');
            darkBorder.className = 'darkBorderBg-btn';
            
            const border = document.createElement('div');
            border.className = 'border-btn';
            
            // Wrap button
            button.parentNode.insertBefore(wrapper, button);
            wrapper.appendChild(glow);
            wrapper.appendChild(darkBorder);
            wrapper.appendChild(border);
            wrapper.appendChild(button);
        }
    });
});
