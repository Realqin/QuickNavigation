pipeline {
    agent {
        node {
            label '192.168.6.189-arm'
        }
    }

    environment {
        GIT_URL = 'git@gitlab.bj.uniseas.com.cn:testdevplat/QuickNavigation.git'
        credentialsId = 'bf6a6f76-deb5-4390-9ec2-ae5c1c03e2ef'
        GIT_BRANCH = 'online_base0709'
        DEPLOY_DIR = '/opt/hlx/QuickNavigation'
        WECHAT_WEBHOOK_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=cfc97a19-6a54-4800-84c6-d3534cbdcf14'
    }

    stages {
        stage('检出代码') {
            steps {
                script {
                    checkout([
                        $class: 'GitSCM',
                        branches: [[name: "*/${env.GIT_BRANCH}"]],
                        extensions: [],
                        userRemoteConfigs: [[
                            credentialsId: env.credentialsId,
                            url: env.GIT_URL
                        ]]
                    ])
                }
            }
        }

        stage('构建前端') {
            steps {
                dir('frontend') {
                    sh '''
                        set -e
                        docker run --rm -v "$PWD:/app" -w /app node:20-alpine sh -c "npm ci && npm run build"
                        test -d dist
                    '''
                }
            }
        }

        stage('发布') {
            steps {
                sh '''
                    set -e
                    rsync -a --delete \
                      --exclude .git \
                      --exclude node_modules \
                      --exclude frontend/node_modules \
                      --exclude offline \
                      --exclude data/api-repos \
                      ./ "${DEPLOY_DIR}/"
                    rsync -a frontend/dist/ "${DEPLOY_DIR}/frontend/dist/"
                    bash "${DEPLOY_DIR}/scripts/ci/deploy-prod.sh"
                '''
            }
        }
    }

    post {
        success {
            sh '''
                curl -sS -X POST "${WECHAT_WEBHOOK_URL}" \
                  -H 'Content-Type: application/json' \
                  -d '{"msgtype":"text","text":{"content":"QuickNavigation 发布成功\nhttp://192.168.6.189:8080"}}' || true
            '''
        }
        failure {
            sh '''
                curl -sS -X POST "${WECHAT_WEBHOOK_URL}" \
                  -H 'Content-Type: application/json' \
                  -d '{"msgtype":"text","text":{"content":"QuickNavigation 发布失败，请查看 Jenkins 日志"}}' || true
            '''
        }
    }
}
