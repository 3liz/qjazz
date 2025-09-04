//
// Copyright 2018 3liz
// Author: David Marteau
//
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.
//

PROCESSES = new Map()

var current_page = 1
var page_limit=10

/* 
 *  Pagination
 */

function get_current_page_limit() {
    page_limit = document.getElementById('page-limit').value
}


async function on_page_limit_change(el) {
    page_limit = el.value
    await get_status(true)
}

async function next_page() {
    current_page = current_page + 1
    console.log("Current page is " + current_page)
    await get_status(true)
}

async function prev_page() {
    current_page = current_page - 1
    console.log("Current page is " + current_page)
    await get_status(true)
}

function update_pagination(links) {
    // Check for rel 'next' link
    let el_next = document.getElementById('next-page')
    let el_prev = document.getElementById('previous-page')
    let disableNext = true
    let disablePrev = true
    for (let res of links) {
        if (res.rel == 'next') {
            disableNext = false
        }
        if (res.rel == 'prev') {
            disablePrev = false
        }
    }
    el_next.classList.toggle("disabled", disableNext)
    el_prev.classList.toggle("disabled", disablePrev)

}

///////////////////////////////////


function get_pr_status( pr_data ) {
    // Return the status of
    if (pr_data.status == 'failed') {
        return 'error';
    }
    if (pr_data.status == 'successful') {
        return 'done'
    }
    if (pr_data.status == 'pending') {
        return 'pending'
    }
    if (pr_data.status == 'accepted') {
        return 'wait'
    }
    if (pr_data.status == 'running') {
        return 'run'        
    }
    if (pr_data.status == 'dismissed') {
        return 'dismiss'        
    }
    return 'none';
}


function format_iso_date( isodate ) {
    // Format an iso date to local date
    return (new Date(isodate)).toLocaleString();
}


function set_label( el, name, value ) {
    // Set the value of a label from the parent
    let lbl = el.querySelector('[name='+name+']')
    lbl.dataset.value = value
    return lbl
}


function update_progressbar( el, value ) {
    if (value !== undefined) {
        let progress = el.querySelector('[name=pr-progress] .progress-bar')
        progress.setAttribute('aria-valuenow', value )
        progress.style.width = value+'%'
    }
}


function add_process( pr_data ) {
    // Get our template
    let t  = document.getElementById("pr-template")
    let fragment = t.content.cloneNode(true)
    // Update attributes
    let pr = fragment.firstElementChild
    pr.setAttribute("id"    , pr_data.jobId)
    pr.setAttribute("status", get_pr_status(pr_data))
    // Update tooltip
    pr.querySelector(".pr-st-box").setAttribute("title" , pr_data.message)
    // Alg identifier 
    let link = set_label( pr, 'alg-name', pr_data.processId)
 
    link.setAttribute('href', `../jobs/${ pr_data.jobId }.html`)

    // Job tag
    set_label( pr, 'job-tag', pr_data.tag === undefined ? "": pr_data.tag)

    // Get the start-date label
    set_label( pr, 'start-date' , format_iso_date(pr_data.created))
    set_label( pr, 'finish-date', format_iso_date(pr_data.finished))


    // Set actions 
    pr.querySelector("[role=pr-delete]").addEventListener('click', function() {
        delete_process(pr_data.jobId)
    })

    // Progress
    update_progressbar( pr, pr_data.progress )
    // Insert it
    let pr_list = document.getElementById("pr-list")
    pr_list.appendChild(fragment)
}


function update_process( pr_data ) {
    // Get our template
    let pr  = document.getElementById(pr_data.jobId)
    if (pr) {
        // Update attributes
        st = get_pr_status(pr_data)
        // status changed
        if (pr.getAttribute("status") != st) {
            pr.setAttribute("status", st)
            pr.setAttribute("title" , pr_data.message)
            set_label( pr, 'job-tag', pr_data.tag === undefined ? "": pr_data.tag)
            set_label( pr, 'start-date' , format_iso_date(pr_data.created))
            set_label( pr, 'finish-date', format_iso_date(pr_data.finished))
        }
        // update progress bar
        update_progressbar( pr, pr_data.progress )
    } else {
        add_process( pr_data )
    }
    // See https://getbootstrap.com/docs/5.0/components/tooltips/#example-enable-tooltips-everywhere
    // For jquery alternative
    $('[data-toggle="tooltip"]').tooltip();
}


async function delete_process( uuid, dontask = false) {
   if(confirm(`Are you sure to delete results:\n${ uuid } ?`)) {
        pr = document.getElementById(uuid)
        st = pr.getAttribute("status")
        if (st == "run") { pr.setAttribute("cancelling", "true") }
        response = await fetch(`../jobs/${ uuid }`, {
            credentials: 'same-origin',
            method: 'DELETE'
        })
       if (st == "run" && ! response.ok) { return
       }
       pr = document.getElementById(uuid)
       if (pr) {
           pr.remove()
       }
   }

}


function update_summary() {
   states = {
      'wait' : 0,
      'error': 0,
      'run': 0,
      'done' : 0
   }
   for(let key of PROCESSES.keys()) {
        e = document.getElementById(key)
        states[e.getAttribute('status')] += 1
   }
   el = document.getElementById('pr-summary')
   for(let k of ['wait','error','run','done']) {
        set_label(el, 'pr-'+k+'-count', states[k])
   }
}


/*
 * Details
 */


function show_details( pr_data ) {
    document.getElementById('pr-raw-link').setAttribute('href','../' + pr_data.jobId)
    for(let key in pr_data) {
        el = document.querySelector('#lbl-'+key)
        if (el) {
            let value = pr_data[key]
            if (value !== undefined) {
                let dtype = el.getAttribute("dtype")
                if (dtype == "date") {
                    value = format_iso_date(value)
                }
            } else {
                value = ""
            }
            el.dataset.value = value
        }
    }
}


async function get_details_status(uuid) {
    console.log("Refreshing status: " + uuid)
    let response = await fetch(`../${uuid}?details=y`, { 
        credentials: 'same-origin'
    })
    if (! response.ok) {
        return
    }    
    let pr_data = await response.json()
    show_details(pr_data)
    refresh_store(pr_data.jobId)
    refresh_log(pr_data.jobId)
    refresh_inputs(pr_data.runConfig)
}


async function refresh_store( uuid ) {
    /* Update file list */
    $("#store-table tbody").empty()
    console.log("Refreshing store: " + uuid)
    let response = await fetch('../' + uuid + '/files/', { 
        credentials: 'same-origin'
    })
    if (! response.ok) {
        return
    }
    data = await response.json()
    for (let res of data['files']) {
         insert_resource_details(res)
    }
}


function insert_resource_details( res ) {
    let t  = document.getElementById("tr-file-template")
    let fragment = t.content.cloneNode(true)
    // Update attributes
    let tr = fragment.firstElementChild
    set_label( tr, 'f-name', res.title).setAttribute('href', res.href)
    // Get the start-date label
    set_label(tr, 'f-type' , res.type)
    set_label(tr, 'f-size' , res.displaySize)
    // Insert it
    document.getElementById("store-table-body").appendChild(fragment)
}


async function refresh_log( uuid ) {
    console.log("Refreshing log: " + uuid)
    let response = await fetch('../' + uuid + '/log', { 
        credentials: 'same-origin'
    })
    if (! response.ok) {
        return
    }
    let data = await response.json()
    el = document.getElementById('pane-log')
    set_label( el, 'log-content' , data.log )
}


function refresh_inputs( data ) {
    data = JSON.stringify(data, undefined, 2)
    el = document.getElementById('pane-inputs')
    set_label( el, 'inputs-content' , data )
}


async function refresh_details() {
    let path = (new URL(document.location)).pathname
    let uuid = path.split('/')[2].split('.')[0]
    await get_details_status(uuid)
}

/*
 * Dashboard
 */

async function get_status(sort=false) {
    console.log("Refreshing status")
    let response = await fetch(`../jobs/?limit=${page_limit}&page=${current_page}`, { 
        credentials: 'same-origin'
    })
    if (! response.ok) {
        return
    }

    let data = await response.json();
    let newMap = new Map()
    // Sort data by start date
    if (sort) {
        data['jobs'].sort(function(a,b){return a.created.localeCompare(b.created)})
    }
    for (let pr_data of data['jobs']) {
         update_process(pr_data)
         newMap.set(pr_data.jobId, pr_data)
    } 
    // Clean up unreferenced data
    for (let key of PROCESSES.keys()) {
        if (newMap.get(key) === undefined) {
            let pr = document.getElementById(key)
            if (pr)
                pr.remove()
        }
    }
    PROCESSES = newMap
    update_summary()
    update_pagination(data['links'])
}


async function run_dashboard()
{
    get_current_page_limit()

    // XXX Retrieve job's realm
    await get_status(true)
    setInterval( get_status, 5000 )
}


/*
 * Bootstrap Init stuff
 */
$(document).ready(function(){
    $('[data-toggle="tooltip"]').tooltip();
});

