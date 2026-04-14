/**
 * SEBC — Main JavaScript
 * Micro-interactions & UI enhancements
 */

document.addEventListener('DOMContentLoaded', () => {

    // ── Intersection Observer for fade-in animations ──
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const fadeObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                fadeObserver.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Apply to stat-cards & feature-cards
    document.querySelectorAll('.stat-card, .feature-card').forEach((card, i) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = `opacity 0.5s ease ${i * 0.08}s, transform 0.5s ease ${i * 0.08}s`;
        fadeObserver.observe(card);
    });

    // ── Active nav link handling ──
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            e.currentTarget.classList.add('active');
        });
    });

    // ── Notification bell pulse ──
    const bellBtn = document.getElementById('btn-notifications');
    if (bellBtn) {
        bellBtn.addEventListener('click', () => {
            const badge = bellBtn.querySelector('.badge');
            if (badge) {
                badge.style.transform = 'scale(0)';
                setTimeout(() => badge.remove(), 200);
            }
        });
    }

    console.log('%c🎓 SEBC — Projet initialisé avec succès', 'color: #6366f1; font-weight: bold; font-size: 14px;');
});
