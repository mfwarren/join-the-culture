function toggleSuper(id) {
    var el = document.getElementById('super-' + id);
    var content = el.querySelector('.super-post-content');
    var toggle = el.querySelector('.super-post-toggle');
    content.classList.toggle('collapsed');
    toggle.textContent = content.classList.contains('collapsed') ? 'Read more' : 'Show less';
}
