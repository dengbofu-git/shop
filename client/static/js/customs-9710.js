/**
 * 9710一键报关核心操作页 - 交互逻辑
 * 一键申报演示动画、折叠面板、步骤联动
 */
(function() {
    'use strict';

    // 折叠面板：报关知识小百科
    var wikiToggle = document.getElementById('wiki-toggle');
    var wikiContent = document.getElementById('wiki-content');
    if (wikiToggle && wikiContent) {
        wikiToggle.addEventListener('click', function() {
            wikiContent.classList.toggle('collapsed');
            wikiToggle.classList.toggle('collapsed');
        });
    }

    // 一键申报演示动画
    var btnDeclare = document.getElementById('btn-declare');
    var modal = document.getElementById('declare-modal');
    var modalSteps = document.getElementById('modal-steps');
    var btnCloseModal = document.getElementById('btn-close-modal');

    if (btnDeclare && modal) {
        btnDeclare.addEventListener('click', function() {
            if (btnDeclare.disabled) return;
            btnDeclare.disabled = true;
            modal.classList.add('show');

            var steps = modalSteps ? modalSteps.querySelectorAll('.modal-step') : [];
            var statuses = ['submitting', 'reviewing', 'tax', 'released'];
            var delays = [800, 1500, 1200, 1000];

            function runStep(index) {
                if (index >= steps.length) {
                    btnDeclare.disabled = false;
                    return;
                }
                steps[index].classList.add('active');
                if (index > 0) {
                    steps[index - 1].classList.remove('active');
                    steps[index - 1].classList.add('done');
                }
                setTimeout(function() {
                    runStep(index + 1);
                }, delays[index]);
            }

            runStep(0);
        });
    }

    if (btnCloseModal && modal) {
        btnCloseModal.addEventListener('click', function() {
            modal.classList.remove('show');
            var steps = modalSteps ? modalSteps.querySelectorAll('.modal-step') : [];
            steps.forEach(function(s) {
                s.classList.remove('active', 'done');
            });
        });
    }

    // 点击遮罩关闭弹窗
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
                var steps = modalSteps ? modalSteps.querySelectorAll('.modal-step') : [];
                steps.forEach(function(s) {
                    s.classList.remove('active', 'done');
                });
            }
        });
    }

    // 步骤导航点击联动（演示用）
    var stepItems = document.querySelectorAll('.step-item');
    stepItems.forEach(function(item) {
        item.addEventListener('click', function() {
            var step = parseInt(item.getAttribute('data-step'), 10);
            stepItems.forEach(function(s, i) {
                var sNum = parseInt(s.getAttribute('data-step'), 10);
                s.classList.remove('done', 'active', 'pending');
                if (sNum < step) {
                    s.classList.add('done');
                    var check = s.querySelector('.step-check');
                    if (check) check.textContent = '✓';
                } else if (sNum === step) {
                    s.classList.add('active');
                    var check = s.querySelector('.step-check');
                    if (check) check.textContent = '';
                } else {
                    s.classList.add('pending');
                    var check = s.querySelector('.step-check');
                    if (check) check.textContent = '';
                }
            });
        });
    });
})();
