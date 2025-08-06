// script.js (replace the entire content of script.js with this)

document.addEventListener('DOMContentLoaded', () => {
    // --- Navbar Active Link Logic (Existing) ---
    const navLinks = document.querySelectorAll('.nav-link-item');
    const currentPage = window.location.pathname.split('/').pop();

    navLinks.forEach(link => {
        link.classList.remove('active-link');

        if (currentPage === 'index.html' && link.id === 'business-link') {
            link.classList.add('active-link');
        } else if (currentPage === 'driver.html' && link.id === 'drivers-link') {
            link.classList.add('active-link');
        }
    });

    // --- Smooth Scrolling Logic (Existing) ---
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            if (this.getAttribute('href').length > 1 && this.getAttribute('href').startsWith('#')) {
                 e.preventDefault();
                 document.querySelector(this.getAttribute('href')).scrollIntoView({
                     behavior: 'smooth'
                 });
            }
        });
    });

    // --- Driver Features Section Animation Logic (Existing) ---
    const featureCards = document.querySelectorAll('.feature-card-animate');
    const driverFeaturesSection = document.querySelector('.driver-features-section');

    if (driverFeaturesSection && featureCards.length > 0) {
        const observer = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    featureCards.forEach((card, index) => {
                        setTimeout(() => {
                            card.classList.add('animate-in');
                        }, index * 200);
                    });
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.3
        });

        observer.observe(driverFeaturesSection);
    }

    // --- NEW: Testimonial Carousel Logic (Rewritten) ---
    const carouselTrack = document.querySelector('.carousel-track');
    const testimonialCards = Array.from(document.querySelectorAll('.testimonial-card')); // Convert to Array
    const carouselDotsContainer = document.querySelector('.carousel-dots');

    if (carouselTrack && testimonialCards.length > 0) {
        let currentIndex = 0;
        let autoRotateInterval;
        let isTransitioning = false; // Flag to prevent rapid clicks

        // --- Helper Functions ---
        const getCardWidth = () => {
            if (testimonialCards.length === 0) return 0;
            // Get the actual width of one card plus its horizontal margins
            const cardRect = testimonialCards[0].getBoundingClientRect();
            const cardComputedStyle = getComputedStyle(testimonialCards[0]);
            const marginLeft = parseFloat(cardComputedStyle.marginLeft);
            const marginRight = parseFloat(cardComputedStyle.marginRight);
            return cardRect.width + marginLeft + marginRight;
        };

        const updateDots = () => {
            carouselDotsContainer.innerHTML = ''; // Clear existing dots
            testimonialCards.forEach((_, index) => {
                const dot = document.createElement('div');
                dot.classList.add('dot');
                if (index === currentIndex) {
                    dot.classList.add('active');
                }
                dot.addEventListener('click', () => {
                    if (!isTransitioning) {
                        goToSlide(index);
                        startAutoRotate();
                    }
                });
                carouselDotsContainer.appendChild(dot);
            });
        };

        const applyCardStates = () => {
            testimonialCards.forEach((card, index) => {
                card.classList.remove('is-active', 'is-prev', 'is-next');
                card.style.transform = ''; // Reset transform for recalculation
                card.style.opacity = ''; // Reset opacity
                card.style.zIndex = ''; // Reset z-index
                card.style.pointerEvents = ''; // Reset pointer-events
            });

            // Determine visible cards based on screen size
            let visibleCardsCount;
            if (window.innerWidth <= 768) {
                visibleCardsCount = 1; // On mobile, only one active card
            } else {
                visibleCardsCount = 3; // On desktop/tablet, active + 2 peeking
            }

            // Set active card
            const activeCard = testimonialCards[currentIndex];
            if (activeCard) {
                activeCard.classList.add('is-active');
            }

            // Set prev/next peeking cards
            const prevIndex = (currentIndex - 1 + testimonialCards.length) % testimonialCards.length;
            const nextIndex = (currentIndex + 1) % testimonialCards.length;

            const prevCard = testimonialCards[prevIndex];
            const nextCard = testimonialCards[nextIndex];

            if (visibleCardsCount > 1) { // Apply peeking styles only if more than 1 card visible
                if (prevCard) prevCard.classList.add('is-prev');
                if (nextCard) nextCard.classList.add('is-next');
            }
        };

        
        const goToSlide = (index) => {
            if (isTransitioning) return;
            isTransitioning = true;

            currentIndex = index;
            applyCardStates(); // Apply states *before* transform for smooth animation

            const cardWidth = getCardWidth();
            let offset = -currentIndex * cardWidth;

            if (window.innerWidth <= 768) {
            } else if (window.innerWidth <= 1024) { // Tablet (center 1 card, show 2 peeking)
               
                const viewportCenter = window.innerWidth / 2;
                const activeCardCenter = activeCard.getBoundingClientRect().left + activeCard.getBoundingClientRect().width / 2;
                const currentOffset = parseFloat(carouselTrack.style.transform.replace('translateX(', '').replace('px)', '') || 0);

                // Calculate the new transform to center active card
                offset = currentOffset + (viewportCenter - activeCardCenter);
            } else { 
                 const centralCardPos = testimonialCards[currentIndex].offsetLeft;
                 const trackOffset = (carouselTrack.offsetWidth / 2) - (cardWidth / 2); 
                 offset = -(centralCardPos - trackOffset);

                
            }

            carouselTrack.style.transform = `translateX(${offset}px)`;

            // After animation completes, reset flag
            setTimeout(() => {
                isTransitioning = false;
            }, 800); // Matches transition duration
        };





        // --- Navigation Functions ---
        const nextSlide = () => {
            goToSlide((currentIndex + 1) % testimonialCards.length);
        };

        const prevSlide = () => {
            goToSlide((currentIndex - 1 + testimonialCards.length) % testimonialCards.length);
        };

        // --- Auto Rotation ---
        const startAutoRotate = () => {
            clearInterval(autoRotateInterval);
            autoRotateInterval = setInterval(nextSlide, 4000); // Auto-rotate every 4 seconds
        };

        // --- Event Listeners & Initial Setup ---
        // Initial setup calls
        updateDots();
        applyCardStates();
        goToSlide(currentIndex); // Ensure correct initial position
        startAutoRotate();

        // Pause auto-rotate on hover (optional)
        carouselTrack.addEventListener('mouseenter', () => clearInterval(autoRotateInterval));
        carouselTrack.addEventListener('mouseleave', startAutoRotate);

        // Recalculate on window resize for responsiveness
        window.addEventListener('resize', () => {
            updateDots(); // Re-render dots
            applyCardStates(); // Re-apply states for new sizes
            goToSlide(currentIndex); // Adjust position
        });
    }
});