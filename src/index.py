import base64
import json
import logging
import os
from http.client import HTTPSConnection
from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)
api_endpoint = 'qdk67n9gl2.execute-api.us-east-1.amazonaws.com'


def doRender(tname, values={}):
    if not os.path.isfile(os.path.join(os.getcwd(), 'templates/' + tname)):  # No such file
        return render_template('index.htm')
    return render_template(tname, **values)


# catch all other page requests - doRender checks if a page is available (shows it) or not (index)
@app.route('/', defaults={'path': ''})
def get_root(path):
    if path:
        return doRender(path)
    else:
        c = HTTPSConnection(api_endpoint)
        c.request('GET', '/Prod/assets')
        response = c.getresponse()
        assets = json.loads(response.read().decode())
        for asset in assets:
            del (asset['path'])
        assets = sorted(assets, key=lambda a: int(a['id']))
        return doRender('index.htm', {'assets': assets})


@app.route('/analyses')
def get_analyses():
    c = HTTPSConnection(api_endpoint)
    c.request('GET', '/Prod/riskAnalyses')
    response = c.getresponse()
    analyses = json.loads(response.read().decode())
    for analysis in analyses:
        del (analysis['path'])
    analyses = sorted(analyses, key=lambda a: int(a['id']))
    return doRender('analyses.htm', {'analyses': analyses})


@app.route('/analyses/<int:id>')
def get_analysis(id):
    c = HTTPSConnection(api_endpoint)
    c.request('GET', '/Prod/riskAnalyses/' + str(id))
    response = c.getresponse()
    analysis = json.loads(response.read().decode())
    df = pd.read_json(json.dumps(analysis.get('data')))
    ts_chart = analysis_to_base64_chart(df)
    total_p_l = None
    avg_var_95 = None
    avg_var_99 = None
    if 'average_var_95' in analysis:
        total_p_l = analysis.get('total_p_l')
        avg_var_95 = analysis.get('average_var_95')
        avg_var_99 = analysis.get('average_var_99')
        sig_df = df.loc[df['var_95'].notna(), ['Date', 'sig', 'p_l', 'var_95', 'var_99']]
    else:
        sig_df = df.loc[df['sig'].notna() & (df['sig'] != 0), ['Date', 'sig', 'p_l']]
    sig_df['sig'] = sig_df['sig'].map({1: 'Buy', -1: 'Sell'}, na_action='ignore')
    sig_html = sig_df.to_html()
    del (analysis['data'])
    return doRender('analysis.htm',
                    {'analysis': analysis, 'ts_chart': ts_chart, 'total_p_l': total_p_l, 'avg_var_95': avg_var_95,
                     'avg_var_99': avg_var_99, 'sig_table': sig_html})


def analysis_to_base64_chart(df):
    plt.figure()
    plt.plot(df['Date'], df['Adj Close'], label='Adj Close')
    plt.plot(df['Date'], df['ma'], color='magenta', label='Moving Average')
    date_last_position = df.loc[df['sig'].notna() & (df['sig'] != 0), 'Date'].iloc[-1]
    plt.axvline(x=date_last_position, color='#c77a24', label='Last trading position')
    plt.legend()
    fig_file = BytesIO()
    plt.savefig(fig_file, format='png')
    fig_file.seek(0)
    fig_data_png = base64.b64encode(fig_file.getvalue())
    fig_file.close()
    ts_chart = fig_data_png.decode('utf8')
    return ts_chart


@app.route('/analyses', methods=['POST'])
def post_analysis():
    if request.method == 'POST':
        payload = {
            'id': request.form.get('id'),
            'ma_period': request.form.get('ma-period'),
            'var_window': request.form.get('var-window'),
            'mc_samples': request.form.get('mc-samples'),
            'scalable_services': request.form.get('scalable-services'),
            'parallel_resources': request.form.get('parallel-resources')
        }
        body = json.dumps(payload)
        c = HTTPSConnection(api_endpoint)
        c.request('POST', '/Prod/riskAnalyses', body)
        response = c.getresponse()
        new_analysis_id = response.msg.get('location')
        return redirect(url_for('get_analyses') + '/' + new_analysis_id)


@app.route('/<path:path>')
def any_path(path):
    return doRender('path_error.htm', {'path': path})


@app.errorhandler(500)
# A small bit of error handling
def server_error(e):
    logging.exception('ERROR!')
    return """An error occurred: <pre>{}</pre>""".format(e), 500


if __name__ == '__main__':
    # Entry point for running on the local machine
    # On GAE, endpoints (e.g. /) would be called.
    # Called as: gunicorn -b :$PORT index:app,
    # host is localhost; port is 8080; this file is index (.py)
    app.run(host='127.0.0.1', port=8080, debug=True)
