let SessionLoad = 1
let s:so_save = &g:so | let s:siso_save = &g:siso | setg so=0 siso=0 | setl so=-1 siso=-1
let v:this_session=expand("<sfile>:p")
silent only
silent tabonly
cd ~/workspace/scripts/awsh_wip
if expand('%') == '' && !&modified && line('$') <= 1 && getline(1) == ''
  let s:wipebuf = bufnr('%')
endif
let s:shortmess_save = &shortmess
if &shortmess =~ 'A'
  set shortmess=aoOA
else
  set shortmess=aoO
endif
badd +113 awsh_gui.py
badd +27 gui/region_view.py
badd +2109 ~/.cache/awsh/info
badd +484 gui/region_view_ctrl.py
badd +431 awsh_client.py
badd +80 awsh_utils.py
badd +734 awsh_ec2.py
badd +249 awsh_req_resp_server.py
badd +1 awsh.py
badd +171 awsh_server.py
badd +125 ~/workspace/scripts/awsh_wip/awsh_cache.py
badd +6 gui/instances_view.py
badd +143 gui/instance.py
badd +47 ~/.config/nvim/init.vim
badd +91 ~/.vim/plugins/nvim-lsp.vim
badd +5 ~/.vim/plugins/luasnip.vim
badd +101 ~/workspace/scripts/awsh_wip/awsh_cli.py
badd +7 ~/workspace/scripts/awsh_wip/awsh_ui.py
badd +262 gui/fuzzy_list_search.py
argglobal
%argdel
$argadd awsh_gui.py
edit gui/region_view_ctrl.py
let s:save_splitbelow = &splitbelow
let s:save_splitright = &splitright
set splitbelow splitright
wincmd _ | wincmd |
vsplit
1wincmd h
wincmd w
let &splitbelow = s:save_splitbelow
let &splitright = s:save_splitright
wincmd t
let s:save_winminheight = &winminheight
let s:save_winminwidth = &winminwidth
set winminheight=0
set winheight=1
set winminwidth=0
set winwidth=1
exe 'vert 1resize ' . ((&columns * 106 + 106) / 212)
exe 'vert 2resize ' . ((&columns * 105 + 106) / 212)
argglobal
balt ~/.cache/awsh/info
let s:l = 379 - ((37 * winheight(0) + 24) / 48)
if s:l < 1 | let s:l = 1 | endif
keepjumps exe s:l
normal! zt
keepjumps 379
normal! 0
wincmd w
argglobal
if bufexists(fnamemodify("gui/region_view_ctrl.py", ":p")) | buffer gui/region_view_ctrl.py | else | edit gui/region_view_ctrl.py | endif
if &buftype ==# 'terminal'
  silent file gui/region_view_ctrl.py
endif
balt ~/.cache/awsh/info
let s:l = 484 - ((33 * winheight(0) + 24) / 48)
if s:l < 1 | let s:l = 1 | endif
keepjumps exe s:l
normal! zt
keepjumps 484
normal! 044|
wincmd w
2wincmd w
exe 'vert 1resize ' . ((&columns * 106 + 106) / 212)
exe 'vert 2resize ' . ((&columns * 105 + 106) / 212)
tabnext 1
if exists('s:wipebuf') && len(win_findbuf(s:wipebuf)) == 0 && getbufvar(s:wipebuf, '&buftype') isnot# 'terminal'
  silent exe 'bwipe ' . s:wipebuf
endif
unlet! s:wipebuf
set winheight=1 winwidth=20
let &shortmess = s:shortmess_save
let &winminheight = s:save_winminheight
let &winminwidth = s:save_winminwidth
let s:sx = expand("<sfile>:p:r")."x.vim"
if filereadable(s:sx)
  exe "source " . fnameescape(s:sx)
endif
let &g:so = s:so_save | let &g:siso = s:siso_save
set hlsearch
nohlsearch
let g:this_session = v:this_session
let g:this_obsession = v:this_session
doautoall SessionLoadPost
unlet SessionLoad
" vim: set ft=vim :
