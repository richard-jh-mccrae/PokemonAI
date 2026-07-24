/* ============================================================================
   PokemonAI teaching — reusable retrieval-practice quiz widget.
   Second shared component. Zero dependencies; works over file://.

   Markup contract (kept dead simple so any lesson can reuse it):

     <div class="quiz">
       <div class="q" data-answer="a">
         <p class="stem">Question text…</p>
         <ul class="opts">
           <li><button class="opt" data-k="a">Option A</button></li>
           <li><button class="opt" data-k="b">Option B</button></li>
           …
         </ul>
         <p class="fb ok"  data-for="ok">Feedback shown on a correct pick.</p>
         <p class="fb no"  data-for="no">Feedback shown on a wrong pick.</p>
       </div>
       …more .q…
       <p class="score"></p>   <!-- optional running tally -->
     </div>

     <!-- spaced-retrieval reveal item -->
     <div class="reveal">
       <button class="rv">Show answer</button>
       <div class="ans">Hidden answer…</div>
     </div>

   Design notes tied to the teaching method:
   - Immediate feedback = the tight loop that builds storage strength.
   - First pick is the graded one (locks the question) so it is genuine recall,
     not multiple-guess. Learner still sees which option was right.
   ============================================================================ */
(function () {
  function gradeQuestion(q, onGraded) {
    var answer = (q.getAttribute("data-answer") || "").trim();
    var buttons = Array.prototype.slice.call(q.querySelectorAll("button.opt"));
    var fbOk = q.querySelector(".fb[data-for='ok']");
    var fbNo = q.querySelector(".fb[data-for='no']");
    var done = false;

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (done) return;
        done = true;
        var pick = btn.getAttribute("data-k");
        var correct = pick === answer;

        buttons.forEach(function (b) {
          b.disabled = true;
          var k = b.getAttribute("data-k");
          if (k === answer) b.classList.add("reveal-ok");     // always show the truth
        });
        btn.classList.add(correct ? "pick-ok" : "pick-no");

        var fb = correct ? fbOk : fbNo;
        if (fb) fb.classList.add("show");
        onGraded(correct);
      });
    });
  }

  function initQuiz(quiz) {
    var questions = Array.prototype.slice.call(quiz.querySelectorAll(".q"));
    var scoreEl = quiz.querySelector(".score");
    var total = questions.length, answered = 0, right = 0;

    function tally(correct) {
      answered += 1; if (correct) right += 1;
      if (scoreEl) {
        scoreEl.textContent = "Recall: " + right + " / " + answered +
          (answered === total ? "  — done. Re-take it cold next session (spacing)." : " answered");
      }
    }
    questions.forEach(function (q) { gradeQuestion(q, tally); });
  }

  function initReveals(root) {
    Array.prototype.slice.call(root.querySelectorAll(".reveal")).forEach(function (r) {
      var btn = r.querySelector("button.rv");
      var ans = r.querySelector(".ans");
      if (!btn || !ans) return;
      btn.addEventListener("click", function () {
        var open = ans.classList.toggle("show");
        btn.textContent = open ? "Hide answer" : "Show answer";
      });
    });
  }

  function boot() {
    Array.prototype.slice.call(document.querySelectorAll(".quiz")).forEach(initQuiz);
    initReveals(document);
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
