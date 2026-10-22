/* eslint-env es11 */
/* jshint esversion: 11 */
/* global window, console */

// Dynamic Tiptap extension: embed YouTube videos in djangocms-text.
//
// This is a plain IIFE with no Tiptap imports. It uses only the primitives
// handed to the factory by the host's registry on window.CMS_Editor.tiptap
// (the same pattern as djangocms_text.contrib.officepaste), so no second copy
// of Tiptap/ProseMirror is loaded.
//
// The node is stored as a plain <iframe> pointing at the privacy-enhanced
// youtube-nocookie.com embed URL.  Only YouTube embed iframes are recognised
// when HTML is parsed; any other <iframe> is dropped by the editor.

(function () {
    'use strict';

    if (!window.CMS_Editor || !window.CMS_Editor.tiptap) {
        console.warn('[danceschool.youtube] window.CMS_Editor.tiptap registry not found, skipping');
        return;
    }

    const api = window.CMS_Editor.tiptap;

    const EMBED_BASE = 'https://www.youtube-nocookie.com/embed/';
    const VIDEO_ID = /^[\w-]{11}$/;
    const EMBED_SRC = /^https:\/\/www\.youtube(?:-nocookie)?\.com\/embed\/([\w-]{11})(?:[?#].*)?$/;

    // Convert any common YouTube URL (or a bare 11-character video ID) to the
    // canonical embed URL.  Returns null if it is not recognisable.
    function toEmbedUrl(input) {
        if (typeof input !== 'string') {
            return null;
        }
        const text = input.trim();
        if (VIDEO_ID.test(text)) {
            return EMBED_BASE + text;
        }

        let url;
        try {
            url = new URL(text);
        } catch (e) {
            return null;
        }
        if (url.protocol !== 'https:' && url.protocol !== 'http:') {
            return null;
        }

        const host = url.hostname.replace(/^(www|m)\./, '');
        let id = null;

        if (host === 'youtu.be') {
            id = url.pathname.slice(1).split('/')[0];
        } else if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
            if (url.pathname === '/watch') {
                id = url.searchParams.get('v');
            } else {
                const m = url.pathname.match(/^\/(?:embed|shorts|live|v)\/([\w-]{11})/);
                id = m ? m[1] : null;
            }
        }

        return id && VIDEO_ID.test(id) ? EMBED_BASE + id : null;
    }

    api.register('danceschool-youtube', ({Node, mergeAttributes}) => Node.create({
        name: 'youtube',
        group: 'block',
        atom: true,
        draggable: true,

        addAttributes() {
            return {
                src: {default: null},
                width: {default: 640},
                height: {default: 360},
            };
        },

        parseHTML() {
            return [{
                tag: 'iframe[src]',
                getAttrs: (el) => {
                    const m = (el.getAttribute('src') || '').match(EMBED_SRC);
                    if (!m) {
                        // Not a YouTube embed: refuse to parse it.
                        return false;
                    }
                    return {
                        src: EMBED_BASE + m[1],
                        width: el.getAttribute('width') || 640,
                        height: el.getAttribute('height') || 360,
                    };
                },
            }];
        },

        renderHTML({HTMLAttributes}) {
            return ['iframe', mergeAttributes(HTMLAttributes, {
                frameborder: '0',
                allowfullscreen: 'true',
                allow: 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share',
                title: 'YouTube video',
                // YouTube refuses to play embeds that arrive with no referrer
                // ("video player configuration error" / error 153), which
                // happens under Django's default Referrer-Policy: same-origin.
                referrerpolicy: 'strict-origin-when-cross-origin',
            })];
        },

        addCommands() {
            return {
                setYoutubeVideo: (options) => ({commands}) => {
                    const src = toEmbedUrl(options && options.src);
                    if (!src) {
                        return false;
                    }
                    return commands.insertContent({
                        type: this.name,
                        attrs: {src, width: options.width, height: options.height},
                    });
                },
            };
        },
    }), {apiVersion: 1});

    api.registerToolbarItem('Youtube', {
        type: 'block',
        title: 'YouTube video',
        icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" ' +
              'fill="currentColor" viewBox="0 0 16 16">' +
              '<path d="M8.051 1.999h.089c.822.003 4.987.033 6.11.335a2.01 2.01 0 0 1 ' +
              '1.415 1.42c.101.38.172.883.22 1.402l.01.104.022.26.008.104c.065.914.073 ' +
              '1.77.074 1.957v.075c-.001.194-.01 1.108-.082 2.06l-.008.105-.009.104c-.05.572' +
              '-.124 1.14-.235 1.558a2.01 2.01 0 0 1-1.415 1.42c-1.16.312-5.569.334-6.18.335h' +
              '-.142c-.309 0-1.587-.006-2.927-.052l-.17-.006-.087-.004-.171-.007-.171-.007c' +
              '-1.11-.049-2.167-.128-2.654-.26a2.01 2.01 0 0 1-1.415-1.419c-.111-.417-.185-.986' +
              '-.235-1.558L.09 9.82l-.008-.104A31 31 0 0 1 0 7.68v-.123c.002-.215.01-.958.064' +
              '-1.778l.007-.103.003-.052.008-.104.022-.26.01-.104c.048-.519.119-1.023.22-1.402' +
              'a2.01 2.01 0 0 1 1.415-1.42c.487-.13 1.544-.21 2.654-.26l.17-.007.172-.006.086' +
              '-.003.171-.007A100 100 0 0 1 7.858 2zM6.4 5.209v4.818l4.157-2.408z"/></svg>',
        action: (editor) => {
            const input = window.prompt('YouTube video URL');
            if (!input) {
                return;
            }
            if (!editor.chain().focus().setYoutubeVideo({src: input}).run()) {
                window.alert('That does not look like a YouTube video URL.');
            }
        },
        enabled: (editor) => !!editor.schema.nodes.youtube,
        active: (editor) => editor.isActive('youtube'),
    });
})();
