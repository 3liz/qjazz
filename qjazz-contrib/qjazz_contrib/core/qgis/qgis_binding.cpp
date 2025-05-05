#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sip.h>
#include <qgis/qgsproject.h>
#include <qgis/server/qgsmapserviceexception.h>
#include <qgis/server/qgsrequesthandler.h>
#include <qgis/server/qgsserver.h>
#include <qgis/server/qgsserverapi.h>
#include <qgis/server/qgsserverapicontext.h>
#include <qgis/server/qgsserverparameters.h>
#include <qgis/server/qgsserverrequest.h>
#include <qgis/server/qgsserverresponse.h>
#include <qgis/server/qgsservice.h>

extern "C" {

#if !defined(SIP_USE_PYCAPSULE)
    #error "SIP_USE_PYCAPSULE not defined !"
#endif

static const sipAPIDef* sip_api = NULL;
static const sipTypeDef* sip_QgsServer_t = NULL;
static const sipTypeDef* sip_QgsProject_t = NULL;
static const sipTypeDef* sip_QgsServerResponse_t = NULL;
static const sipTypeDef* sip_QgsServerRequest_t = NULL;

static const sipTypeDef* sip_find_type(const char* name)
{
    const sipTypeDef* st = (const sipTypeDef*)sip_api->api_find_type(name);
    if (!st) 
    {
        PyErr_SetString(PyExc_RuntimeError, name);
        return NULL;
    }
    return st;
}

bool sip_setup() 
{
    sip_api = (const sipAPIDef*)PyCapsule_Import("PyQt5.sip._C_API", 0);
    if (!sip_api) 
    {
        PyErr_SetString(PyExc_RuntimeError, "Cannot get sip C API");
        return false;
    }
 
    sip_QgsServer_t = sip_find_type("QgsServer");
    if (!sip_QgsServer_t)
        return false;
   
    sip_QgsProject_t = sip_find_type("QgsProject");
    if (!sip_QgsProject_t)
        return false;

    sip_QgsServerResponse_t = sip_find_type("QgsServerResponse");
    if (!sip_QgsServerResponse_t)
        return false;

    sip_QgsServerRequest_t = sip_find_type("QgsServerRequest");
    if (!sip_QgsServerRequest_t)
        return false;

    return true;
}


}

template<typename T>
static T* convert_to(PyObject* sw, const sipTypeDef* st, const char* expect) 
{
    int state, iserr = 0;

    /* Check object type */
    if (Py_IsNone(sw) || !sip_api->api_can_convert_to_type(sw, st, 0))
    {
        PyErr_SetString(PyExc_ValueError, expect);
        return NULL;
    }

    void* addr;

    /* Unwrap address */
    if (!(addr = sip_api->api_convert_to_type(sw, st, NULL, 0, &state, &iserr))) 
    {
        PyErr_SetString(PyExc_RuntimeError, "Failed to convert SIP object");
        return NULL;
    }

    return static_cast<T*>(addr);
}


extern "C" {

    static PyObject* ServerExc_ApiNotFoundError;
    static PyObject* ServerExc_InternalError;
    static PyObject* ServerExc_ProjectRequired;
}

// Methods implementations


// XXX: python errors in plugins filters are
// returned as XML content with the raw python exception message. 
// This is a security concern and we prevent leaking internal infos
// by returning the error as a generic 500 error without the error message.
void set_internal_error(QgsServerResponse& response, QgsException& exc, QString location) 
{
    response.setHeader(QStringLiteral("Content-Type"), QStringLiteral("text/plain"));
    response.sendError(500, QStringLiteral("Internal Server Error"));
    QgsMessageLog::logMessage(
        QString("%1 (location: %2)").arg(exc.what()).arg(location), 
        QStringLiteral("Qjazz"), 
        Qgis::MessageLevel::Critical);
}

struct Filters 
{
    QgsServerFiltersMap filters;

    bool request_ready(QgsRequestHandler& handler, QgsServerResponse& response) {
        if (!filters.empty()) {
            try {
                QgsServerFiltersMap::const_iterator filtersIterator;
                for (filtersIterator = filters.constBegin(); filtersIterator != filters.constEnd(); 
                    ++filtersIterator) {
                    if (!filtersIterator.value()->onRequestReady())
                        break;
                }
            } catch (QgsException &exc) {
                set_internal_error(response, exc, QStringLiteral("request ready"));
                return false;
            }

            // plugin may have set exception
            if (handler.exceptionRaised() || (response.feedback() && 
                 response.feedback()->isCanceled()))
            {
                response.finish();
                return false;
            }
        }
        return true;
    }

    bool project_ready(QgsRequestHandler& handler, QgsServerResponse& response) {
        if (!filters.empty()) {
            try {
                QgsServerFiltersMap::const_iterator filtersIterator;
                for (filtersIterator = filters.constBegin(); filtersIterator != filters.constEnd(); 
                    ++filtersIterator ) {
                    if (!filtersIterator.value()->onProjectReady())
                        break;
                }
            } catch (QgsException &exc) {
                set_internal_error(response, exc, QStringLiteral("project ready"));
                return false;
            }

            // plugin may have set exception
            if (handler.exceptionRaised() || (response.feedback() && 
                 response.feedback()->isCanceled()))
            {
                response.finish();
                return false;
            }
        }
        return true;
    }

    bool response_complete(QgsRequestHandler& handler, QgsServerResponse& response) {
        if (!filters.empty()) {
            try {
                QgsServerFiltersMap::const_iterator filtersIterator;
                for (filtersIterator = filters.constBegin(); filtersIterator != filters.constEnd();
                    ++filtersIterator ) {
                    if (!filtersIterator.value()->onResponseComplete())
                        break;
                }
            } catch (QgsException &exc) {
                set_internal_error(response, exc, QStringLiteral("response complete"));
                return false;
            }

            if (handler.exceptionRaised() || (response.feedback() &&
                response.feedback()->isCanceled())) 
            {
                response.finish();
                return false;
            }
        }
        return true;
    }
};


// RIAA Guard
struct Guard {
    QgsServerInterfaceImpl* iface;

    ~Guard() {
        iface->clearRequestHandler();
        QgsProject::setInstance(NULL);
    }

}; 


bool handle_request_impl(
    QgsServer& server,
    QgsServerRequest& request,
    QgsServerResponse& response,
    const QgsProject* project,
    const char* api_name
) 
{
    QgsServerInterfaceImpl* iface = server.serverInterface();

    qApp->processEvents();
 
    QgsServerApi* api = NULL;
    if (api_name)
    {
        // Find the api 
        if(!(api = iface->serviceRegistry()->getApi(api_name)))
        {
            PyErr_SetString(ServerExc_ApiNotFoundError, api_name);
            return false;
        } 
    } 
    else 
    {
        // Project is mandatory
        if (!project) {
            PyErr_SetString(ServerExc_ProjectRequired, api_name);
            return false; 
        }
    }
  
    // Clean up qgis access control filter's cache: prevent side effects
    // across requests
    QgsAccessControl *accesscontrols = iface->accessControls();
    if (accesscontrols) 
        accesscontrols->unresolveFilterFeatures();

    QgsRequestHandler handler(request, response);
    try {
        handler.parseInput();
    } catch (QgsMapServiceException &e) {
        QgsMessageLog::logMessage("Parse input exception: " + e.message(), 
            QStringLiteral("Qjazz"),
            Qgis::MessageLevel::Critical
        );
        if (api) {
            response.write(QgsServerException(e.message(), 400));         
        } else {
            response.write(e);
        };
        response.finish();
        return true;
    }

    iface->setConfigFilePath(project ? project->fileName() : QString());
    iface->setRequestHandler(&handler);  

    Guard guard { iface };

    Filters filters { iface->filters() };

    if (!filters.request_ready(handler, response))
        return true;

    // XXX The dreaded QgsProject singleton
    QgsProject::setInstance(const_cast<QgsProject*>(project));
 
    if (!filters.project_ready(handler, response)) 
        return true;
    
    try {
        if (api) {
            // Handle API request
            const QgsServerApiContext context { 
                api->rootPath(), 
                &request, 
                &response,
                project,
                iface,
            };
            api->executeRequest(context);
        }
        else
        {  
            // Handle OWS request
            // Note that filters may change parameters
            const QgsServerParameters params = request.serverParameters();
            // XXX: What is the purpose of this ?
            if (!params.fileName().isEmpty()) {
                handler.setResponseHeader(
                    QStringLiteral("Content-Disposition"),
                    QString("attachment; filename=\"%1\"").arg(params.fileName())
                );
            }

            QgsService *service = iface->serviceRegistry()->getService(
                params.service(),
                params.version()
            );

            if (!service) {
                response.write(QgsOgcServiceException(
                    QStringLiteral("Service configuration error"),
                    QStringLiteral("Service unknown or unsupported")         
                ));
                response.finish();    
                return true;
            }
            
            service->executeRequest(request, response, project);
        }
    }
    catch (QgsServerException &exc) {
        response.write(exc);
        response.finish();
        return true;
    }
    catch (QgsException &exc) {
        set_internal_error(response, exc, QStringLiteral("request execute"));
        return true;
    }

    if (filters.response_complete(handler, response))
        response.finish();

    return true;
}



extern "C" {

//===================
// Server object type
//===================

// From https://docs.python.org/3/extending/newtypes_tutorial.html
typedef struct {
    PyObject_HEAD
    /* custom fields */
    // Keep reference of the QgsServer python object
    PyObject* ob_wrapper;
    // The unwrapped QgsServer pointer 
    QgsServer *ob_server;
    char use_default_handler;
} Server;

// __delete__
static void Server_dealloc(Server* self)
{
    Py_XDECREF(self->ob_wrapper);
    Py_TYPE(self)->tp_free((PyObject *) self);
}

// __init__
static int Server_init(Server* self, PyObject *args)
{
    PyObject* sw;
    if (!PyArg_ParseTuple(args, "O", &sw))
        return -1;

    QgsServer *addr = convert_to<QgsServer>(sw, sip_QgsServer_t, "Expecting QgsServer");
    if (!addr) 
        return -1;

    Py_XSETREF(self->ob_wrapper, Py_NewRef(sw));
    
    self->ob_server = addr;
    self->use_default_handler = 0;
    return 0; 
}

// Methods

// handle_request
static PyObject* Server_handle_request(Server* self, PyObject* args, PyObject *kwargs) 
{
    static const char* kwds[] = {"request", "response", "project", "api", NULL};

    PyObject* request_w;
    PyObject* response_w;
    PyObject* project_w = NULL;

    const char* api = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|Os", (char**)kwds,
        &request_w,
        &response_w,
        &project_w,
        &api
     ))
        return NULL;

    QgsServerRequest* request = convert_to<QgsServerRequest>(
        request_w,
        sip_QgsServerRequest_t,
        "QgsServerRequest Expected"
    );
    if (!request)
        return NULL;

    QgsServerResponse* response = convert_to<QgsServerResponse>(
        response_w,
        sip_QgsServerResponse_t,
        "QgsServerRequest expected"
    );
    if (!response)
        return NULL;

    QgsProject *project = NULL;
    if (project_w && !Py_IsNone(project_w))
        project = convert_to<QgsProject>(project_w, sip_QgsProject_t, "QgsProject expected");

    try {
        if (self->use_default_handler) {
            // Fallback to the default handler
            self->ob_server->handleRequest(*request, *response, project);
        } else {
            if(!handle_request_impl(*self->ob_server, *request, *response, project, api))
                return NULL;
        }
    } catch (...) {
        PyErr_SetString(ServerExc_InternalError, "Unhandled exception");
        return NULL;
    }
    Py_RETURN_NONE;
}


static PyMethodDef Server_methods[] = {
    {"handle_request", (PyCFunction) Server_handle_request, METH_VARARGS|METH_KEYWORDS,
     "Handle request"},
    {NULL}
};


// Getters

static PyObject* Server_getinner(Server* self, void* closure)
{
    return Py_NewRef(self->ob_wrapper);
} 

static PyGetSetDef Server_getsetters[] {
    {"inner", (getter) Server_getinner, NULL, "Inner QGIS server instance", NULL},
    {NULL}
};


// Members

static PyMemberDef Server_members[] {
    {"use_default_handler", Py_T_BOOL, offsetof(Server, use_default_handler), 0,
        "Use the default server request handler"},
    {NULL}
};


// NOTE: C++ generate error for unordered designator
static PyTypeObject ServerType = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "qgis_binding.Server",
    .tp_basicsize = sizeof(Server),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor) Server_dealloc, 
    .tp_flags = Py_TPFLAGS_DEFAULT |  Py_TPFLAGS_BASETYPE, // Define as subtypable
    .tp_doc = PyDoc_STR("QGIS Server wrapper"),
    .tp_methods = Server_methods,
    .tp_members = Server_members,
    .tp_getset = Server_getsetters,
    .tp_init = (initproc) Server_init,
    .tp_new = PyType_GenericNew,
};


static PyMethodDef QgisBindingMethods[] = {
    {NULL, NULL, 0, NULL}
};


static struct PyModuleDef qgis_binding_module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "qgis_binding",
    .m_doc = NULL, /* module documentation */
    .m_size = -1,   /* size of per-interpreter state of the module, or -1 if the module keeps state in
             global variables */
    .m_methods = QgisBindingMethods,
};


static PyObject* add_new_exception(PyObject* m, const char* qualname, const char* name)
{
    PyObject* error = PyErr_NewException(qualname, NULL, NULL);
    Py_XINCREF(error);
    if (PyModule_AddObject(m, name, error) < 0) {
        Py_XDECREF(error);
        Py_CLEAR(error);
        Py_DECREF(m);
        return NULL;
    }
    return error;
}


PyMODINIT_FUNC PyInit_qgis_binding(void)
{
    if (!sip_setup())
        return NULL;

    if (PyType_Ready(&ServerType) < 0)
        return NULL;

    PyObject *m = PyModule_Create(&qgis_binding_module);
    if (!m)
        return NULL;

    if (PyModule_AddObjectRef(m, "Server", (PyObject *)&ServerType) < 0) 
    {
        Py_DECREF(&ServerType);
        Py_DECREF(m);
        return NULL;
    }

    // Add exceptions:
    ServerExc_ApiNotFoundError = add_new_exception(m, 
        "qgis_binding.ApiNotFoundError",
        "ApiNotFoundError"
    );
    if (!ServerExc_ApiNotFoundError)
        return NULL;

    ServerExc_InternalError = add_new_exception(m,
        "qgis_binding.InternalError",
        "InternalError"
    );
    if (!ServerExc_InternalError)
        return NULL;

    ServerExc_ProjectRequired = add_new_exception(m,
        "qgis_binding.ProjectRequired",
        "ProjectRequired"
    );
    if (!ServerExc_ProjectRequired)
        return NULL;

    return m;
}


} // Extern C
